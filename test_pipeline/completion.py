"""Evaluates the "Greenhouse baseline complete" streak criteria, per
joyful-sprouting-swan.md's "Completion criteria" section. Deliberately not
named/framed as "Greenhouse is done" — see that section's own reasoning
for why (a falsifiable, honestly-scoped claim, not a closure claim).

The 5 conditions, all required:
    1. >= 500 Phase-A AND >= 500 Phase-B jobs attempted.
    2. The most recent 150 consecutive jobs SINCE THE LAST ACCEPTED FIX,
       counted separately per phase, show zero new clusters meeting the
       occurrence threshold.
    3. Every accepted fix has a passing regression entry (100% on
       check_regressions.js, checked against the CURRENT real repo state).
    4. All tracked quality signals hold or improve at the final checkpoint
       vs. the first — replay.py coverage_pct not lower, mismatch_pct not
       higher, and no RISING share of interpreter_pattern_collision late
       in the run's cumulative design-layer histogram.
    5. Every "needs a human decision" cluster has been explicitly resolved
       (accepted as a new category, or consciously deferred) — none left
       silently open.

"Since the last accepted fix" (#2) has no dedicated timestamp table —
every accepted fix becomes a git commit touching extension/filler_utils.js
and/or corpus_analysis/interpreter_p14.py per the plan's own approval step
(git apply + commit), so git log against those two files IS the durable
record of when a fix landed. Reusing it avoids inventing a second source
of truth that could drift from what git already knows for certain.

Public API:
    CompletionEvaluation      — full result (dataclass)
    evaluate_completion(...)  -> CompletionEvaluation
"""

import dataclasses
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import test_pipeline.db_state as db_state
from test_pipeline.checkpoint.cluster import Cluster
from test_pipeline.checkpoint.propose_fix import NeedsHumanDecision

logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent.parent

_VOLUME_TARGET_PER_PHASE = 500
_CONSECUTIVE_CLEAN_TARGET = 150

# Watched files per the plan's own "since the last accepted fix" anchor —
# same two files propose_fix.py is allowed to autonomously touch.
_WATCHED_FILES = ["extension/filler_utils.js", "corpus_analysis/interpreter_p14.py"]


@dataclasses.dataclass
class ConditionResult:
    name: str
    passed: bool
    detail: str


@dataclasses.dataclass
class CompletionEvaluation:
    conditions: list[ConditionResult]
    unresolved_human_decisions: list[NeedsHumanDecision]

    @property
    def complete(self) -> bool:
        return all(c.passed for c in self.conditions) and not self.unresolved_human_decisions

    def summary_text(self) -> str:
        lines = ["Greenhouse baseline complete: " + ("YES" if self.complete else "NOT YET"), ""]
        for c in self.conditions:
            lines.append(f"  [{'x' if c.passed else ' '}] {c.name} — {c.detail}")
        if self.unresolved_human_decisions:
            lines.append(f"  [ ] {len(self.unresolved_human_decisions)} needs-human-decision cluster(s) still open")
        return "\n".join(lines)


def get_last_accepted_fix_timestamp(since: datetime | None = None) -> datetime | None:
    """Most recent commit timestamp touching either watched file, per the
    project's real git history — the "since the last accepted fix" anchor
    for criterion #2. Returns None if no such commit exists at all (a run
    with zero accepted fixes yet — the whole run counts toward the streak
    in that case)."""
    args = ["git", "log", "-1", "--format=%aI", "--"] + _WATCHED_FILES
    try:
        out = subprocess.run(args, cwd=PROJECT_DIR, capture_output=True, text=True, check=True)
        ts_str = out.stdout.strip()
        if not ts_str:
            return None
        return datetime.fromisoformat(ts_str)
    except Exception:
        logger.warning("Could not determine last accepted-fix commit timestamp", exc_info=True)
        return None


async def _check_volume(run_id: int) -> ConditionResult:
    counts_a = await db_state.get_outcome_counts(run_id, sample_phase="A")
    counts_b = await db_state.get_outcome_counts(run_id, sample_phase="B")
    total_a = sum(counts_a.values())
    total_b = sum(counts_b.values())
    passed = total_a >= _VOLUME_TARGET_PER_PHASE and total_b >= _VOLUME_TARGET_PER_PHASE
    return ConditionResult(
        name="Volume (>=500 Phase-A and >=500 Phase-B jobs attempted)",
        passed=passed,
        detail=f"Phase A: {total_a}/{_VOLUME_TARGET_PER_PHASE}, Phase B: {total_b}/{_VOLUME_TARGET_PER_PHASE}",
    )


async def _check_consecutive_clean_since_last_fix(run_id: int) -> ConditionResult:
    """Per-phase: the most recent 150 outcomes must ALL be
    mechanically_verified, restricted to jobs that ENDED after the last
    accepted fix's commit timestamp (or the whole run, if no fix has
    landed yet). A phase with fewer than 150 qualifying jobs since the
    last fix has not yet met this bar — not an error, just not there yet."""
    last_fix_ts = get_last_accepted_fix_timestamp()

    details = []
    both_pass = True
    for phase in ("A", "B"):
        # Pull a generous window (not just the target size) so filtering
        # by timestamp still leaves enough candidates to judge the streak
        # honestly, rather than truncating to fewer than 150 before the
        # filter is even applied.
        recent = await db_state.get_recent_outcomes_with_timestamps(
            run_id, phase, limit=_CONSECUTIVE_CLEAN_TARGET * 4,
        )
        if last_fix_ts is not None:
            recent = [r for r in recent if r["ended_at"] > last_fix_ts]

        window = recent[:_CONSECUTIVE_CLEAN_TARGET]
        if len(window) < _CONSECUTIVE_CLEAN_TARGET:
            since_note = f" since last fix ({last_fix_ts.isoformat()})" if last_fix_ts else ""
            details.append(f"Phase {phase}: only {len(window)}/{_CONSECUTIVE_CLEAN_TARGET} jobs completed{since_note}")
            both_pass = False
            continue
        all_clean = all(r["outcome"] == "mechanically_verified" for r in window)
        details.append(f"Phase {phase}: last {_CONSECUTIVE_CLEAN_TARGET} outcomes all mechanically_verified = {all_clean}")
        both_pass = both_pass and all_clean

    return ConditionResult(
        name=f"{_CONSECUTIVE_CLEAN_TARGET} consecutive mechanically_verified per phase, since last accepted fix",
        passed=both_pass,
        detail="; ".join(details),
    )


async def _check_no_recent_clusters_meeting_threshold(recent_clusters: list[Cluster]) -> ConditionResult:
    """Cross-checks criterion #2's spirit directly against cluster.py's own
    output for the checkpoints covering the consecutive-clean window,
    rather than relying solely on outcome counts — a belt-and-suspenders
    check the plan doesn't separately name but that's implied by "zero new
    clusters meeting the occurrence threshold." Caller passes in whatever
    clusters were found across the relevant recent checkpoints."""
    meeting = [c for c in recent_clusters if c.meets_threshold]
    return ConditionResult(
        name="Zero clusters meeting occurrence threshold in the recent window",
        passed=(len(meeting) == 0),
        detail=(
            "No clusters met threshold in the window checked." if not meeting
            else f"{len(meeting)} cluster(s) still meeting threshold: "
                 + ", ".join(f"{c.fingerprint.reason_code}/{c.fingerprint.category_attempted}" for c in meeting[:5])
        ),
    )


def _check_all_accepted_fixes_have_regression_entries() -> ConditionResult:
    """Criterion #3: 100% on check_regressions.js against the CURRENT real
    repo state (not a scratch copy — this is checking the accumulated,
    already-applied fixes, which by the time this runs are just the real
    committed files)."""
    try:
        result = subprocess.run(
            ["node", "corpus_analysis/check_regressions.js"],
            cwd=PROJECT_DIR, capture_output=True, text=True, timeout=120,
        )
        passed = result.returncode == 0
        last_line = [l for l in result.stdout.splitlines() if l.strip()][-1] if result.stdout.strip() else ""
        return ConditionResult(
            name="Every accepted fix has a passing regression entry (check_regressions.js)",
            passed=passed, detail=last_line or f"exit_code={result.returncode}",
        )
    except Exception as exc:
        logger.error("check_regressions.js failed to run", exc_info=True)
        return ConditionResult(
            name="Every accepted fix has a passing regression entry (check_regressions.js)",
            passed=False, detail=f"Could not run check_regressions.js: {exc}",
        )


def _check_quality_signals_hold_or_improve(
    first_checkpoint_replay: dict,
    final_checkpoint_replay: dict,
    cumulative_histogram_first_half: dict[str, float],
    cumulative_histogram_second_half: dict[str, float],
) -> ConditionResult:
    """Criterion #4. Caller supplies the first and final checkpoint's
    replay.py reports (report.py/gate.py already produce these; completion.py
    doesn't re-run replay itself) and the design-layer histogram computed
    over the run's first half vs. second half of accepted fixes."""
    coverage_ok = final_checkpoint_replay.get("coverage_pct", 0) >= first_checkpoint_replay.get("coverage_pct", 0)
    mismatch_ok = final_checkpoint_replay.get("mismatch_pct", 100) <= first_checkpoint_replay.get("mismatch_pct", 100)

    first_collision_share = cumulative_histogram_first_half.get("interpreter_pattern_collision", 0.0)
    second_collision_share = cumulative_histogram_second_half.get("interpreter_pattern_collision", 0.0)
    histogram_ok = second_collision_share <= first_collision_share

    passed = coverage_ok and mismatch_ok and histogram_ok
    detail = (
        f"coverage {first_checkpoint_replay.get('coverage_pct')}->{final_checkpoint_replay.get('coverage_pct')} "
        f"({'OK' if coverage_ok else 'REGRESSED'}); "
        f"mismatch {first_checkpoint_replay.get('mismatch_pct')}->{final_checkpoint_replay.get('mismatch_pct')} "
        f"({'OK' if mismatch_ok else 'REGRESSED'}); "
        f"interpreter_pattern_collision share {first_collision_share}%->{second_collision_share}% "
        f"({'OK' if histogram_ok else 'RISING — investigate before declaring complete'})"
    )
    return ConditionResult(
        name="Quality signals hold or improve (coverage, mismatch, design-layer histogram)",
        passed=passed, detail=detail,
    )


def _check_human_decisions_resolved(
    all_needs_human_decision: list[NeedsHumanDecision],
    resolved_job_ids: set[str],
) -> tuple[ConditionResult, list[NeedsHumanDecision]]:
    """Criterion #5. resolved_job_ids is caller-tracked (e.g. a small
    manifest file or manual record of which needs-human-decision items
    have been explicitly closed one way or the other) — completion.py
    doesn't invent a new resolution-tracking mechanism, it just checks
    whatever the caller says has been resolved against what's outstanding."""
    unresolved = [
        item for item in all_needs_human_decision
        if not any(m.job_id in resolved_job_ids for m in item.cluster.members)
    ]
    return ConditionResult(
        name="Every needs-human-decision cluster explicitly resolved (accepted or deferred)",
        passed=(len(unresolved) == 0),
        detail=("All resolved." if not unresolved else f"{len(unresolved)} still open."),
    ), unresolved


async def evaluate_completion(
    run_id: int,
    recent_clusters: list[Cluster],
    first_checkpoint_replay: dict,
    final_checkpoint_replay: dict,
    cumulative_histogram_first_half: dict[str, float],
    cumulative_histogram_second_half: dict[str, float],
    all_needs_human_decision: list[NeedsHumanDecision],
    resolved_job_ids: set[str],
) -> CompletionEvaluation:
    """Evaluates all 5 conditions. Most inputs are things report.py/gate.py
    already compute at each checkpoint — completion.py is a pure evaluator
    over already-known facts, not a new data-collection pass, except for
    the two DB reads (volume, consecutive-clean) and the two subprocess
    checks (regressions, git log) it owns directly."""
    volume = await _check_volume(run_id)
    consecutive_clean = await _check_consecutive_clean_since_last_fix(run_id)
    clusters_clean = await _check_no_recent_clusters_meeting_threshold(recent_clusters)
    regressions = _check_all_accepted_fixes_have_regression_entries()
    quality = _check_quality_signals_hold_or_improve(
        first_checkpoint_replay, final_checkpoint_replay,
        cumulative_histogram_first_half, cumulative_histogram_second_half,
    )
    human_decisions, unresolved = _check_human_decisions_resolved(all_needs_human_decision, resolved_job_ids)

    return CompletionEvaluation(
        conditions=[volume, consecutive_clean, clusters_clean, regressions, quality, human_decisions],
        unresolved_human_decisions=unresolved,
    )
