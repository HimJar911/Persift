"""One persistent `claude` CLI session per ATS, driven as a subprocess.
Authenticates via whatever Claude Code login is already active on this
machine (subscription-billed), NOT an API key -- this is the entire reason
the decision agent runs locally instead of on the VM via Managed Agents.

Session persistence: the first call for an ATS mints a session id and
spawns with the full briefing prompt (project docs, hard file-write
ceiling, authority scope). Every later call for the same ATS passes
--resume <session_id>, so the agent's context (prior decisions, the
project docs it already read) carries forward without re-sending them --
this is the actual point of "one persistent agent per ATS, resumed across
the whole effort" from the design discussion, not a fresh spawn per
checkpoint.

Public API:
    get_or_create_session(ats: str) -> str          -- session id
    ask(ats: str, prompt: str) -> dict               -- the parsed `claude -p` JSON result
"""

import json
import logging
import shutil
import subprocess
import uuid

from decision_agent import config

logger = logging.getLogger(__name__)

_CLAUDE_TIMEOUT_SECONDS = 1800  # 30 min ceiling per decision -- corpus queries + precedent checks take real time

# subprocess.run(["claude", ...]) without shell=True does NOT resolve
# Windows PATHEXT shims (claude.cmd) the way an interactive shell does --
# confirmed live: raises FileNotFoundError even though `where claude` finds
# it. shutil.which() DOES resolve PATHEXT correctly, so use it to get the
# real executable path once at import time.
_CLAUDE_EXE = shutil.which("claude")
if _CLAUDE_EXE is None:
    raise RuntimeError(
        "claude CLI not found on PATH. decision_agent requires the Claude Code CLI "
        "to be installed and logged in on this machine (subscription auth)."
    )


class ClaudeSessionError(Exception):
    pass


def _load_session_ids() -> dict:
    config.LOCAL_STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not config.SESSION_IDS_FILE.exists():
        return {}
    return json.loads(config.SESSION_IDS_FILE.read_text(encoding="utf-8"))


def _save_session_ids(ids: dict) -> None:
    config.SESSION_IDS_FILE.write_text(json.dumps(ids, indent=2), encoding="utf-8")


def get_or_create_session(ats: str) -> tuple[str, bool]:
    """Returns (session_id, is_new). is_new=True means the caller must
    send the full first-spawn briefing prompt this call AND call
    confirm_session_onboarded() only after that briefing call succeeds --
    the id is intentionally NOT persisted here. Persisting before a
    confirmed-successful briefing was a real bug caught in testing: a crash
    between minting the id and the briefing call actually succeeding (e.g.
    the claude CLI subprocess failing) left an orphaned session-id on disk
    that looked "already onboarded" on the next retry, so a later resume
    call would --resume a session that was never actually briefed."""
    ids = _load_session_ids()
    if ats in ids:
        return ids[ats], False
    return str(uuid.uuid4()), True


def confirm_session_onboarded(ats: str, session_id: str) -> None:
    """Call only after the first-spawn briefing `ask()` call has returned
    successfully (no ClaudeSessionError raised). Persists the session id so
    future get_or_create_session(ats) calls resume it instead of minting
    a fresh, unbriefed one."""
    ids = _load_session_ids()
    ids[ats] = session_id
    _save_session_ids(ids)


def ask(session_id: str, prompt: str, is_new: bool, cwd: str) -> dict:
    """Runs the prompt against the persistent session (new spawn if
    is_new, --resume otherwise). `cwd` MUST be the local checked-out repo
    root -- the agent needs filesystem access to project docs
    (FORM_ENGINE_DESIGN.md, decisions/*.md, corpus_analysis/*.json) to
    ground its decisions, per the design's corpus-grounding requirement.
    Raises ClaudeSessionError on nonzero exit, timeout, or unparseable
    output -- caller should treat this as "no decision this cycle," not
    crash the runner loop."""
    cmd = [
        # -p with NO argument here -- the prompt is piped via stdin below,
        # not passed as an argv element. Confirmed live: claude.CMD is a
        # batch-file shim, and Windows CreateProcess/batch-file argument
        # parsing mangles a multi-line argv string (a real prompt is
        # thousands of chars with embedded newlines and backslashes) --
        # it silently truncates at the first newline, so the model only
        # ever saw "Line one." of a 4-line test prompt. Piping via stdin
        # sidesteps argv parsing entirely and is not Windows-specific
        # brittleness -- it's the correct approach on any platform.
        _CLAUDE_EXE, "-p",
        "--output-format", "json",
        # No TTY is present to approve tool-use prompts in an unattended
        # overnight run -- confirmed live: without this, claude just talks
        # ("let me ask the user how they'd like to proceed") instead of
        # acting or erroring, so the JSON parse fails downstream. The
        # mechanical backstop for this broad grant is
        # guard_forbidden_writes.py, run by runner.py after every commit
        # this session makes -- see that module's docstring.
        "--permission-mode", "bypassPermissions",
    ]
    # --session-id (first spawn, mints a NEW session under that id) and
    # --resume (continue an EXISTING session) are mutually exclusive --
    # confirmed live: passing both errors unless --fork-session is also
    # set, which would branch into a new session rather than continuing
    # the same one, defeating the whole point of session persistence here.
    cmd += ["--session-id", session_id] if is_new else ["--resume", session_id]

    try:
        proc = subprocess.run(
            cmd, cwd=cwd, input=prompt, capture_output=True, text=True, timeout=_CLAUDE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as e:
        raise ClaudeSessionError(f"claude CLI timed out after {_CLAUDE_TIMEOUT_SECONDS}s") from e

    if proc.returncode != 0:
        raise ClaudeSessionError(f"claude CLI exited {proc.returncode}: {proc.stderr[:2000]}")

    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise ClaudeSessionError(f"claude CLI output not valid JSON: {proc.stdout[:2000]}") from e

    if result.get("is_error"):
        raise ClaudeSessionError(f"claude CLI reported an error result: {result.get('result')}")

    logger.info(
        "claude session %s: %d turns, cost $%.4f, stop_reason=%s",
        session_id[:8], result.get("num_turns", 0),
        result.get("total_cost_usd", 0.0), result.get("stop_reason"),
    )
    return result
