"""Entry point. Polls the VM over SSH for pending checkpoint decision
requests, dispatches each to the persistent per-ATS claude session, writes
the decision back for orchestrate.py to pick up. Designed to run
unattended for hours: every VM call is wrapped so a transient SSH/network
failure logs and retries on the next poll tick rather than crashing the
process, and Windows sleep is held off for the whole run via sleep_guard.

Usage: python -m decision_agent.runner
"""

import datetime
import json
import logging
import time

from decision_agent import claude_session, config, guard_forbidden_writes, prompts, sleep_guard, ssh_bridge

config.LOCAL_STATE_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] decision-agent: %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(config.LOG_FILE, encoding="utf-8")],
)
logger = logging.getLogger(__name__)

_REQUEST_GLOB = f"{config.VM_REPO_DIR}/checkpoints/*/checkpoint_*.decision_request.json"
_LOCAL_REPO_DIR = str(config.LOCAL_STATE_DIR.parent.parent)  # decision_agent/state -> decision_agent -> repo root


def _process_one_request(remote_request_path: str) -> None:
    claimed_path = remote_request_path.replace(".decision_request.json", ".decision_request.claimed.json")
    try:
        ssh_bridge.rename_remote_file(remote_request_path, claimed_path)
    except ssh_bridge.SSHError:
        logger.warning("Failed to claim %s (already claimed by a prior run?) -- skipping.", remote_request_path)
        return

    request_json = ssh_bridge.read_remote_file(claimed_path)
    decision_request = json.loads(request_json)

    ats = decision_request["ats"]
    run_id = decision_request["run_id"]
    checkpoint_n = decision_request["checkpoint_n"]
    remote_report_path = f"{config.VM_REPO_DIR}/{decision_request['report_path']}"

    logger.info("New decision request: ats=%s run=%s checkpoint=%s", ats, run_id, checkpoint_n)

    report_markdown = ssh_bridge.read_remote_file(remote_report_path)

    session_id, is_new = claude_session.get_or_create_session(ats)

    if is_new:
        logger.info("First checkpoint for %s -- sending onboarding briefing.", ats)
        briefing_result = claude_session.ask(
            session_id, prompts.build_briefing_prompt(ats), is_new=True, cwd=_LOCAL_REPO_DIR,
        )
        logger.info("Briefing acknowledged: %s", briefing_result.get("result", "")[:200])
        claude_session.confirm_session_onboarded(ats, session_id)

    head_before = _git_head(_LOCAL_REPO_DIR)
    checkpoint_prompt = prompts.build_checkpoint_prompt(decision_request, report_markdown)
    result = claude_session.ask(session_id, checkpoint_prompt, is_new=False, cwd=_LOCAL_REPO_DIR)
    head_after = _git_head(_LOCAL_REPO_DIR)

    reverted = guard_forbidden_writes.check_and_revert_forbidden_writes(_LOCAL_REPO_DIR, head_before, head_after)
    if reverted:
        logger.error("Forbidden-path commit(s) reverted this checkpoint: %s", reverted)

    decisions_payload = _extract_decisions_json(result.get("result", ""))
    if decisions_payload is None:
        logger.error("Could not parse a decisions JSON block from the agent's response -- leaving run halted.")
        return

    response_path = remote_request_path.replace(".decision_request.json", ".decision_response.json")
    response_body = json.dumps(
        {**decisions_payload, "checkpoint_n": checkpoint_n,
         "decided_at": datetime.datetime.now(datetime.timezone.utc).isoformat()},
        indent=2,
    )
    ssh_bridge.write_remote_file(response_path, response_body)
    logger.info("Decision written to %s: %d decisions, resume_run=%s",
                response_path, len(decisions_payload.get("decisions", [])), decisions_payload.get("resume_run"))


def _git_head(repo_dir: str) -> str:
    import subprocess
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_dir, capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def _extract_decisions_json(agent_text: str) -> dict | None:
    """Pulls the fenced ```json block prompts.py's _RESPONSE_FORMAT asks
    for out of the agent's free-text response."""
    marker = "```json"
    start = agent_text.rfind(marker)
    if start == -1:
        return None
    start += len(marker)
    end = agent_text.find("```", start)
    if end == -1:
        return None
    try:
        return json.loads(agent_text[start:end].strip())
    except json.JSONDecodeError:
        return None


def main() -> None:
    logger.info("Decision-agent runner starting. Polling every %ds.", config.POLL_INTERVAL_SECONDS)
    with sleep_guard.keep_awake():
        while True:
            try:
                pending = ssh_bridge.list_remote_files(_REQUEST_GLOB)
            except ssh_bridge.SSHError as e:
                logger.warning("Poll failed (will retry): %s", e)
                time.sleep(config.POLL_INTERVAL_SECONDS)
                continue

            for remote_path in pending:
                try:
                    _process_one_request(remote_path)
                except ssh_bridge.SSHError as e:
                    logger.warning("Processing %s failed (will retry next poll): %s", remote_path, e)
                except claude_session.ClaudeSessionError as e:
                    logger.error("Claude session error on %s (leaving request claimed, needs manual look): %s",
                                 remote_path, e)

            time.sleep(config.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
