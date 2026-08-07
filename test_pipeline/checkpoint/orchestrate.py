"""Ties cluster.py -> propose_fix.py -> gate.py -> report.py together into
one checkpoint pass, and applies the safe subset of fixes automatically.

**Auto-apply scope, confirmed with the user 2026-08-06**: a proposed fix is
auto-applied to the REAL repo (git apply + commit, no scratch copy involved
for this step) only if ALL of the following hold:
    1. It's a ProposedFix (not NeedsHumanDecision/NoGeneralizedFix) — i.e.
       propose_fix.py's narrow negative-guard-only scope already applies.
    2. Its negative_guard_check_passed is True (no conflict with an
       existing regression entry).
    3. gate.py's three checks all pass (regression 100%, zero new parity
       disagreements, replay coverage doesn't drop).
    4. Fewer than AUTO_APPLY_CAP_PER_CHECKPOINT fixes have already been
       auto-applied THIS checkpoint.

Everything else — any NeedsHumanDecision, any NoGeneralizedFix, any
ProposedFix that fails its guardrail or gate, or any ProposedFix beyond the
cap — is left for human review in the checkpoint report. The cap exists as
insurance against a subtle gate blind spot compounding across many fixes
in one unattended pass, same "start conservative" instinct as the circuit
breaker's concurrency default — cheap on the common case, bounds the
downside on an uncommon one.

Public API:
    CheckpointResult          — everything that happened this checkpoint (dataclass)
    run_checkpoint(run_id, checkpoint_n, since, jobs_processed_this_batch,
                    occurrence_threshold_pct, cumulative_accepted_fixes) -> CheckpointResult
"""

import dataclasses
import datetime
import json
import logging
import subprocess
import time
from pathlib import Path

import test_pipeline.db_state as db_state
from test_pipeline.checkpoint.cluster import Cluster, cluster_failures
from test_pipeline.checkpoint.gate import GateResult, run_gate
from test_pipeline.checkpoint.propose_fix import (
    NeedsHumanDecision, NoGeneralizedFix, ProposedFix,
    cleanup_scratch_worktree, propose_fixes_for_clusters,
)
from test_pipeline.checkpoint.report import write_checkpoint_report
from test_pipeline.failure_log import (
    attempts_path_for_run, count_lines, failures_path_for_run,
    read_attempt_records, read_failures_since,
)

logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent

AUTO_APPLY_CAP_PER_CHECKPOINT = 3

# How long to poll for the laptop-side decision agent (decision_agent/) to
# pick up a decision request before giving up and falling back to the
# original "halt the run, human reads the report" behavior. 4 hours covers
# a laptop that's asleep/unreachable for a while but still leaves room for
# a human to notice via the run just... not finishing overnight. See
# decision_agent/README.md for the full protocol this writes/reads.
DECISION_AGENT_POLL_TIMEOUT_SECONDS = 4 * 60 * 60
DECISION_AGENT_POLL_INTERVAL_SECONDS = 15


def _decision_request_path(run_id: int, checkpoint_n: int) -> Path:
    return report_dir_for(run_id) / f"checkpoint_{checkpoint_n:04d}.decision_request.json"


def _streak_halt_request_path(run_id: int, halt_n: int) -> Path:
    # Deliberately a distinct filename pattern from checkpoint_NNNN.* so
    # decision_agent/runner.py's glob for checkpoint requests never
    # accidentally picks up a streak-halt request meant for a different
    # handler, and vice versa.
    return report_dir_for(run_id) / f"streak_halt_{halt_n:04d}.decision_request.json"


def _streak_halt_response_path(run_id: int, halt_n: int) -> Path:
    return report_dir_for(run_id) / f"streak_halt_{halt_n:04d}.decision_response.json"


def _decision_response_path(run_id: int, checkpoint_n: int) -> Path:
    return report_dir_for(run_id) / f"checkpoint_{checkpoint_n:04d}.decision_response.json"


def report_dir_for(run_id: int) -> Path:
    from test_pipeline.checkpoint.report import CHECKPOINTS_DIR
    return CHECKPOINTS_DIR / f"greenhouse_run_{run_id}"


@dataclasses.dataclass
class AppliedFix:
    fix: ProposedFix
    commit_sha: str


@dataclasses.dataclass
class CheckpointResult:
    checkpoint_n: int
    clusters: list[Cluster]
    proposed_fixes: list[ProposedFix]
    needs_human_decision: list[NeedsHumanDecision]
    no_generalized_fix: list[NoGeneralizedFix]
    gate_results: dict  # id(ProposedFix) -> GateResult
    applied_fixes: list[AppliedFix]
    report_path: Path
    halted_for_review: bool


def _apply_fix_to_real_repo(fix: ProposedFix) -> str:
    """Applies fix.diff_js and fix.diff_py directly to the real repo files
    (NOT the scratch copy — that was only ever for gating) and commits.
    Returns the new commit SHA. Uses `git apply` against unified diffs
    gate.py/propose_fix.py already produced via `git diff` in the scratch
    worktree, which apply cleanly against the real files since the scratch
    worktree was branched from the same HEAD the real repo is still at
    (true as long as no other commit landed on filler_utils.js/
    interpreter_p14.py between checkpoint start and this apply — a real,
    small race window, accepted here since checkpoints already serialize:
    the harness's own worker loop is paused while this function runs)."""
    for diff_text, relpath in ((fix.diff_js, "extension/filler_utils.js"),
                                 (fix.diff_py, "corpus_analysis/interpreter_p14.py")):
        if not diff_text.strip():
            continue
        proc = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", "-"],
            cwd=PROJECT_DIR, input=diff_text, capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"git apply failed for {relpath}: {proc.stderr}")

    _append_regression_entry(fix.regression_entry, fix.category)

    subprocess.run(
        ["git", "add", "extension/filler_utils.js", "corpus_analysis/interpreter_p14.py",
         "corpus_analysis/interpreter_regressions.json"],
        cwd=PROJECT_DIR, check=True, capture_output=True, text=True,
    )
    commit_msg = (
        f"Self-healing pipeline: auto-applied negative guard on {fix.category!r} "
        f"(term={fix.guard_term!r})\n\n"
        f"{fix.rationale}\n\n"
        f"Gate-clean (100% regressions, 0 new parity disagreements, replay coverage "
        f"held), auto-applied under the harness's capped auto-apply policy "
        f"(max {AUTO_APPLY_CAP_PER_CHECKPOINT}/checkpoint). design_layer_tag="
        f"interpreter_pattern_collision.\n\n"
        f"Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
    )
    subprocess.run(
        ["git", "commit", "-m", commit_msg],
        cwd=PROJECT_DIR, check=True, capture_output=True, text=True,
    )
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=PROJECT_DIR, check=True, capture_output=True, text=True,
    ).stdout.strip()
    return sha


def _append_regression_entry(entry: dict, category: str) -> None:
    """Fills in expected_capability (left blank by propose_fix.py — see its
    own comment) with the category the guard was added to, since by
    definition a passing negative guard doesn't change what labels DO
    resolve to `category`, only narrows what incorrectly did. Appends to
    the real interpreter_regressions.json, not the scratch copy's."""
    import json
    path = PROJECT_DIR / "corpus_analysis" / "interpreter_regressions.json"
    entries = json.loads(path.read_text(encoding="utf-8"))
    entry = dict(entry)
    entry["expected_capability"] = category
    entries.append(entry)
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")


async def run_checkpoint(
    run_id: int,
    checkpoint_n: int,
    failure_log_lines_at_last_checkpoint: int,
    jobs_processed_this_batch: int,
    cumulative_accepted_fixes: list[dict],
    circuit_breaker_status: dict | None = None,
    new_fingerprints_this_batch: int = 0,
) -> tuple[CheckpointResult, int]:
    """The full checkpoint pass: cluster -> propose -> gate -> apply (capped,
    guard-only, gate-clean) -> report. `failure_log_lines_at_last_checkpoint`
    is the failure-log line count as of the previous checkpoint (0 for the
    first) — used to cluster only failures accumulated SINCE then, not
    re-cluster (and re-gate, at ~5 min/gate-run) already-resolved failures
    every checkpoint. Caller (harness_runner.py) is responsible for having
    paused all workers before calling this and relaunching them after
    (picking up any applied fixes). Returns (result, new_line_count) — the
    caller persists new_line_count as the boundary for the NEXT checkpoint."""
    failures_path = failures_path_for_run(run_id)
    attempts_path = attempts_path_for_run(run_id)

    batch_failure_records = read_failures_since(failures_path, failure_log_lines_at_last_checkpoint)
    new_line_count = count_lines(failures_path)
    # Paired-success lookup still wants the run's FULL attempt history, not
    # just this batch — per cluster.py's own docstring ("800 comboboxes
    # succeed, 20 fail" needs the 800 from anywhere in the run).
    all_attempt_records = list(read_attempt_records(attempts_path))

    clusters = cluster_failures(batch_failure_records, all_attempt_records, jobs_processed_this_batch)

    proposal_results, scratch_dir = propose_fixes_for_clusters(clusters, run_id, checkpoint_n)

    proposed_fixes = [r for r in proposal_results if isinstance(r, ProposedFix)]
    needs_human_decision = [r for r in proposal_results if isinstance(r, NeedsHumanDecision)]
    no_generalized_fix = [r for r in proposal_results if isinstance(r, NoGeneralizedFix)]

    gate_results: dict = {}
    applied_fixes: list[AppliedFix] = []

    try:
        for fix in proposed_fixes:
            if not fix.negative_guard_check_passed:
                logger.info("Fix on %r skipped auto-apply: negative-guard conflict.", fix.category)
                continue

            gr = run_gate(scratch_dir)
            gate_results[id(fix)] = gr

            if not gr.passed:
                logger.info("Fix on %r skipped auto-apply: gate failed.", fix.category)
                continue

            if len(applied_fixes) >= AUTO_APPLY_CAP_PER_CHECKPOINT:
                logger.info(
                    "Fix on %r gate-clean but auto-apply cap (%d) reached this checkpoint — leaving for human review.",
                    fix.category, AUTO_APPLY_CAP_PER_CHECKPOINT,
                )
                continue

            try:
                sha = _apply_fix_to_real_repo(fix)
                applied_fixes.append(AppliedFix(fix=fix, commit_sha=sha))
                logger.info("Auto-applied fix on %r (guard=%r) as commit %s", fix.category, fix.guard_term, sha[:8])
            except Exception:
                logger.error("Failed to apply gate-clean fix on %r to the real repo — leaving for human review.",
                             fix.category, exc_info=True)
    finally:
        if scratch_dir is not None:
            cleanup_scratch_worktree(scratch_dir)

    applied_ids = {id(af.fix) for af in applied_fixes}
    unapplied_fixes = [f for f in proposed_fixes if id(f) not in applied_ids]

    outcome_counts_by_phase = {
        "A": await db_state.get_outcome_counts(run_id, sample_phase="A"),
        "B": await db_state.get_outcome_counts(run_id, sample_phase="B"),
    }
    fingerprints = await db_state.get_distinct_page_fingerprints(run_id)

    new_cumulative = cumulative_accepted_fixes + [
        {"design_layer_tag": af.fix.design_layer_tag} for af in applied_fixes
    ]

    report_path = write_checkpoint_report(
        run_id=run_id, checkpoint_n=checkpoint_n,
        outcome_counts_by_phase=outcome_counts_by_phase,
        circuit_breaker_status=circuit_breaker_status or {
            "block_streak": 0, "streak_threshold": 0, "page_block_tripped": False,
            "page_block_reason": None, "should_halt": False, "should_force_early_checkpoint": False,
        },
        distinct_fingerprints_seen=len(fingerprints), new_fingerprints_this_batch=new_fingerprints_this_batch,
        clusters=clusters, occurrence_threshold_pct=0.02,
        proposed_fixes=proposed_fixes, gate_results=gate_results,
        needs_human_decision=needs_human_decision, no_generalized_fix=no_generalized_fix,
        cumulative_accepted_fixes=new_cumulative,
    )

    # Halt for human review whenever there's something a human actually
    # needs to look at: any needs_human_decision item, or any proposed fix
    # that wasn't auto-applied (failed its gate/guardrail, or was gate-clean
    # but over the cap). A checkpoint where every proposed fix got cleanly
    # auto-applied and there are no open needs_human_decision items does
    # NOT need to halt — that's the whole point of the capped auto-apply
    # path.
    halted_for_review = bool(needs_human_decision) or bool(unapplied_fixes)

    result = CheckpointResult(
        checkpoint_n=checkpoint_n, clusters=clusters, proposed_fixes=proposed_fixes,
        needs_human_decision=needs_human_decision, no_generalized_fix=no_generalized_fix,
        gate_results=gate_results, applied_fixes=applied_fixes,
        report_path=report_path, halted_for_review=halted_for_review,
    )
    return result, new_line_count


def _serialize_needs_human_decision(items: list[NeedsHumanDecision]) -> list[dict]:
    return [{"category": item.cluster.fingerprint.category_attempted, "reason": item.reason} for item in items]


def _serialize_unapplied_fixes(proposed_fixes: list[ProposedFix], applied_fixes: list[AppliedFix],
                                 gate_results: dict) -> list[dict]:
    applied_ids = {id(af.fix) for af in applied_fixes}
    out = []
    for fix in proposed_fixes:
        if id(fix) in applied_ids:
            continue
        if not fix.negative_guard_check_passed:
            reason = "guard_conflict"
        elif id(fix) in gate_results and not gate_results[id(fix)].passed:
            reason = "gate_failed"
        else:
            reason = "over_auto_apply_cap"
        out.append({"category": fix.category, "reason": reason, "guard_term": fix.guard_term})
    return out


def write_decision_request(run_id: int, checkpoint_n: int, result: CheckpointResult, ats: str = "greenhouse") -> Path:
    """Writes the request file the laptop-side decision_agent/ package
    polls for (see decision_agent/README.md for the full protocol). Called
    by harness_runner.py's loop only when result.halted_for_review is True
    and it wants automated review instead of a hard stop."""
    path = _decision_request_path(run_id, checkpoint_n)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "checkpoint_n": checkpoint_n,
        "ats": ats,
        "report_path": str(result.report_path.relative_to(PROJECT_DIR)),
        "needs_human_decision": _serialize_needs_human_decision(result.needs_human_decision),
        "unapplied_fixes": _serialize_unapplied_fixes(result.proposed_fixes, result.applied_fixes, result.gate_results),
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def poll_for_decision_response(
    run_id: int, checkpoint_n: int,
    timeout_seconds: int = DECISION_AGENT_POLL_TIMEOUT_SECONDS,
    poll_interval_seconds: int = DECISION_AGENT_POLL_INTERVAL_SECONDS,
) -> dict | None:
    """Blocks the run loop until decision_agent/runner.py writes the
    matching .decision_response.json, or timeout_seconds elapses (laptop
    unreachable/asleep for too long — caller falls back to the original
    hard-halt behavior). Returns the parsed response dict, or None on
    timeout. Deliberately synchronous (not async) — matches the design
    discussion's explicit choice of blocking/synchronous-per-checkpoint
    invocation, same as gate.py/propose_fix.py already work, no new
    concurrency model needed."""
    response_path = _decision_response_path(run_id, checkpoint_n)
    deadline = time.monotonic() + timeout_seconds
    logger.info("Waiting for decision agent response at %s (timeout %ds)...", response_path, timeout_seconds)
    while time.monotonic() < deadline:
        if response_path.exists():
            try:
                return json.loads(response_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logger.warning("Decision response at %s is not valid JSON yet — retrying (write may be in progress).",
                               response_path)
        time.sleep(poll_interval_seconds)
    logger.warning("Timed out waiting %ds for decision agent response — falling back to hard halt.", timeout_seconds)
    return None


def write_streak_halt_request(run_id: int, halt_n: int, recent_outcomes: list[dict], ats: str = "greenhouse") -> Path:
    """Real gap found live (Aug 7 2026): the outcome-streak circuit breaker
    (distinct from a checkpoint's halted_for_review — see
    circuit_breaker.py) was a hard, unconditional stop with no decision-
    agent involvement at all, even when --use-decision-agent was passed.
    Confirmed live: a genuine 10-in-a-row timeout streak across diverse,
    unrelated companies (not a single blocked domain) tripped it during a
    real overnight-bound run, and the run just sat there — nothing would
    have resumed it until a human noticed. There's no code-fixable bug to
    cluster here (unlike a checkpoint halt), so the question handed to the
    agent is narrower: is this recent stretch ordinary noise safe to
    resume past, or does it look like a genuine systemic problem worth a
    human's attention? recent_outcomes is the raw shape of what tripped
    it (from db_state.get_recent_run_wide_outcomes) — company/ats
    diversity and worker spread are exactly what distinguishes "one
    blocked domain" from "something is actually broken.\""""
    path = _streak_halt_request_path(run_id, halt_n)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "halt_n": halt_n,
        "ats": ats,
        "halt_type": "outcome_streak",
        "recent_outcomes": recent_outcomes,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def poll_for_streak_halt_response(
    run_id: int, halt_n: int,
    timeout_seconds: int = DECISION_AGENT_POLL_TIMEOUT_SECONDS,
    poll_interval_seconds: int = DECISION_AGENT_POLL_INTERVAL_SECONDS,
) -> dict | None:
    """Same blocking-poll shape as poll_for_decision_response, against the
    streak-halt response path instead. Returns the parsed response, or
    None on timeout (caller falls back to the original hard-halt)."""
    response_path = _streak_halt_response_path(run_id, halt_n)
    deadline = time.monotonic() + timeout_seconds
    logger.info("Waiting for decision agent response on streak halt at %s (timeout %ds)...",
                response_path, timeout_seconds)
    while time.monotonic() < deadline:
        if response_path.exists():
            try:
                return json.loads(response_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logger.warning("Streak-halt response at %s is not valid JSON yet — retrying.", response_path)
        time.sleep(poll_interval_seconds)
    logger.warning("Timed out waiting %ds for decision agent streak-halt response — falling back to hard halt.",
                    timeout_seconds)
    return None
