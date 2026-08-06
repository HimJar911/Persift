"""Renders the human-facing checkpoint markdown report, per
joyful-sprouting-swan.md's "Checkpoint pass" §4 — same rationale-first,
table-driven convention as INTERPRETER_SPEC.md/CONSENT_POLICY_SPEC.md.

Pure rendering: takes already-computed data (outcome counts, clusters, fix
proposals, gate results) and writes checkpoints/greenhouse_run_<run_id>/
checkpoint_<NNNN>.md. No new business logic beyond the cumulative
design-layer histogram aggregation, which only report.py needs (nothing
else in the pipeline consumes it).

Public API:
    write_checkpoint_report(...) -> Path
"""

import logging
from pathlib import Path

from test_pipeline.checkpoint.cluster import Cluster
from test_pipeline.checkpoint.gate import GateResult
from test_pipeline.checkpoint.propose_fix import NeedsHumanDecision, NoGeneralizedFix, ProposedFix

logger = logging.getLogger(__name__)

CHECKPOINTS_DIR = Path(__file__).resolve().parent.parent.parent / "checkpoints"

# Never "success"/"clean" anywhere in this report — the schema-level naming
# invariant from migrations/025_harness_run_state.sql and decisions/0010
# extends to the report text itself, per the plan: the report must not be
# able to misstate what was actually checked (mechanical field-landing, not
# semantic correctness).
_MECHANICALLY_VERIFIED_LABEL = "mechanically_verified"


def checkpoint_report_path(run_id: int, checkpoint_n: int) -> Path:
    run_dir = CHECKPOINTS_DIR / f"greenhouse_run_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir / f"checkpoint_{checkpoint_n:04d}.md"


def _outcome_table(outcome_counts_by_phase: dict) -> str:
    """outcome_counts_by_phase = {'A': {outcome: n, ...}, 'B': {...}}."""
    all_outcomes = sorted(set(outcome_counts_by_phase.get("A", {})) | set(outcome_counts_by_phase.get("B", {})))
    if not all_outcomes:
        return "_No jobs completed in this batch._\n"

    lines = ["| Outcome | Phase A | Phase B | Total |", "|---|---|---|---|"]
    for outcome in all_outcomes:
        a = outcome_counts_by_phase.get("A", {}).get(outcome, 0)
        b = outcome_counts_by_phase.get("B", {}).get(outcome, 0)
        label = outcome if outcome != "mechanically_verified" else _MECHANICALLY_VERIFIED_LABEL
        lines.append(f"| {label} | {a} | {b} | {a + b} |")
    return "\n".join(lines) + "\n"


def _circuit_breaker_section(status_summary: dict) -> str:
    lines = ["## Circuit breaker status", ""]
    if status_summary.get("page_block_tripped"):
        lines.append(f"**TRIPPED — page-level block signature detected.** Reason: {status_summary.get('page_block_reason')}")
        lines.append("")
        lines.append("Remaining pending jobs for this run were marked `skipped_blocked` and are not counted toward completion.")
    elif status_summary.get("should_halt"):
        lines.append(f"**TRIPPED — outcome streak crossed threshold.** block_streak={status_summary.get('block_streak')}/{status_summary.get('streak_threshold')}")
    else:
        lines.append(f"OK. block_streak={status_summary.get('block_streak')}/{status_summary.get('streak_threshold')} (no trip).")
    lines.append("")
    return "\n".join(lines)


def _fingerprint_novelty_section(distinct_seen: int, new_this_batch: int) -> str:
    return (
        "## Page-layout fingerprint novelty\n\n"
        f"Distinct page fingerprints seen: {distinct_seen} ({new_this_batch} new this batch). "
        "Not a target to hit (true universe size unknown) — a running signal for whether the "
        "sample is still discovering genuinely new page shapes or has saturated.\n"
    )


def _cluster_summary_line(c: Cluster) -> str:
    fp = c.fingerprint
    status = "**meets threshold**" if c.meets_threshold else "_below threshold — not yet a class_"
    return (
        f"- `{fp.reason_code}` / category=`{fp.category_attempted}` / role=`{fp.role}` / "
        f"html_type=`{fp.html_type}` / id_pattern=`{fp.id_pattern}` — "
        f"{c.occurrence_count} occurrence(s) (threshold={c.occurrence_threshold}) — {status}\n"
        f"  - Example labels: {', '.join(repr(l) for l in c.distinct_labels[:3])}"
        + (f" (+{len(c.distinct_labels) - 3} more)" if len(c.distinct_labels) > 3 else "")
    )


def _clusters_section(clusters: list[Cluster], occurrence_threshold_pct: float) -> str:
    lines = [
        "## Clusters found this checkpoint",
        "",
        f"Minimum occurrence threshold this batch: `max(3, ceil({occurrence_threshold_pct} * jobs_processed))` "
        f"(a stated, visible parameter — not silently hardcoded).",
        "",
    ]
    if not clusters:
        lines.append("_No field-level failure clusters this batch._")
        return "\n".join(lines) + "\n"

    meeting = [c for c in clusters if c.meets_threshold]
    below = [c for c in clusters if not c.meets_threshold]

    lines.append(f"**{len(meeting)} cluster(s) meeting threshold, {len(below)} below threshold (shown, not acted on).**")
    lines.append("")
    for c in clusters:
        lines.append(_cluster_summary_line(c))
        if c.paired_successes:
            lines.append(
                f"  - Paired successes from run history sharing the same structural family: "
                f"{len(c.paired_successes)} example(s) — "
                + ", ".join(repr(s.label) for s in c.paired_successes[:3])
            )
        lines.append("")
    return "\n".join(lines)


def _proposed_fix_section(fix: ProposedFix, gate_result: GateResult | None) -> str:
    fp = fix.cluster.fingerprint
    lines = [
        f"### Proposed fix — `{fix.category}` guard: `{fix.guard_term}`",
        "",
        f"**Design-layer tag:** `{fix.design_layer_tag}`",
        "",
        f"**Cluster:** {fix.cluster.occurrence_count} occurrence(s) of `{fp.reason_code}` on `{fix.category}`.",
        "",
        f"**Rationale:** {fix.rationale}",
        "",
        f"**Negative-guard collision check (against all existing `interpreter_regressions.json` entries):** "
        + ("PASSED — no conflicts." if fix.negative_guard_check_passed else
           f"**FAILED** — would flip: {', '.join(repr(c) for c in fix.negative_guard_conflicts)}"),
        "",
        "**extension/filler_utils.js diff:**",
        "```diff",
        fix.diff_js.strip() or "(no diff)",
        "```",
        "",
        "**corpus_analysis/interpreter_p14.py diff:**",
        "```diff",
        fix.diff_py.strip() or "(no diff)",
        "```",
        "",
    ]

    if gate_result is not None:
        lines += [
            "**Gate results:**",
            "",
            "| Check | Result | Detail |",
            "|---|---|---|",
            f"| check_regressions.js | {'PASS' if gate_result.regression.passed else 'FAIL'} | exit_code={gate_result.regression.exit_code} |",
            f"| parity (new disagreements) | {'PASS' if gate_result.parity.passed else 'FAIL'} | {len(gate_result.parity.new_disagreements)} new |",
            f"| replay.py coverage_pct | {'PASS' if gate_result.replay.passed else 'FAIL'} | "
            f"delta={gate_result.replay.coverage_delta:+.2f} (pre={gate_result.replay.pre_report.get('coverage_pct')}, "
            f"post={gate_result.replay.post_report.get('coverage_pct')}) |",
            f"| replay.py mismatch_pct (non-blocking) | — | delta={gate_result.replay.mismatch_delta:+.2f} |",
            f"| replay.py predicted_unknown_pct (non-blocking) | — | delta={gate_result.replay.unknown_delta:+.2f} |",
            "",
            f"**Overall gate: {'PASS' if gate_result.passed else 'FAIL'}**",
            "",
        ]
    else:
        lines.append("_Gate not yet run for this fix._\n")

    lines.append("- [ ] Approve — apply this diff to the real repo files and commit")
    lines.append("- [ ] Reject")
    lines.append("")
    return "\n".join(lines)


def _needs_human_decision_section(items: list[NeedsHumanDecision]) -> str:
    lines = ["## Clusters needing a human decision (new-concept candidates)", ""]
    if not items:
        lines.append("_None this checkpoint._")
        return "\n".join(lines) + "\n"
    lines.append(
        "`propose_fix.py` deliberately declined to draft a diff for these — they look like they need a "
        "new category/capability/policy entry, not a refinement to an existing pattern, per the hard "
        "invariant against autonomous edits to `category_mapping.py`/`taxonomy_v1.py`/`consent_policy.js`."
    )
    lines.append("")
    for item in items:
        fp = item.cluster.fingerprint
        lines.append(f"- **`{fp.reason_code}` / category=`{fp.category_attempted}`** ({item.cluster.occurrence_count} occurrences)")
        lines.append(f"  - {item.reason}")
        lines.append(f"  - Example labels: {', '.join(repr(l) for l in item.cluster.distinct_labels[:3])}")
        lines.append("  - [ ] Resolved as a new category/capability (separate human-led change)")
        lines.append("  - [ ] Consciously deferred")
        lines.append("")
    return "\n".join(lines)


def _no_generalized_fix_section(items: list[NoGeneralizedFix]) -> str:
    lines = ["## Clusters reviewed, no generalized fix found", ""]
    if not items:
        lines.append("_None this checkpoint._")
        return "\n".join(lines) + "\n"
    lines.append(
        "A checkpoint with zero accepted diffs but a clear \"reviewed, nothing generalizable found\" "
        "writeup is a successful checkpoint, not a failed one."
    )
    lines.append("")
    for item in items:
        fp = item.cluster.fingerprint
        lines.append(f"- **`{fp.reason_code}` / category=`{fp.category_attempted}`** ({item.cluster.occurrence_count} occurrences): {item.reason}")
    lines.append("")
    return "\n".join(lines)


def compute_design_layer_histogram(cumulative_accepted_fixes: list[dict]) -> dict[str, float]:
    """cumulative_accepted_fixes = list of {'design_layer_tag': str} dicts —
    every fix ACCEPTED (approved + applied) so far in the run, not just this
    checkpoint's proposals. Returns tag -> percentage. This is the running
    architectural-investment signal per the plan: "61% interpreter_pattern_
    collision, 24% fill_mechanics, ..." across the whole run so far."""
    if not cumulative_accepted_fixes:
        return {}
    counts: dict[str, int] = {}
    for fix in cumulative_accepted_fixes:
        tag = fix.get("design_layer_tag", "other")
        counts[tag] = counts.get(tag, 0) + 1
    total = len(cumulative_accepted_fixes)
    return {tag: round(100 * n / total, 1) for tag, n in sorted(counts.items(), key=lambda kv: -kv[1])}


def _design_layer_histogram_section(histogram: dict[str, float]) -> str:
    lines = ["## Cumulative design-layer histogram (all accepted fixes so far, this run)", ""]
    if not histogram:
        lines.append("_No fixes accepted yet this run._")
        return "\n".join(lines) + "\n"
    lines.append(
        "The running architectural-investment signal — where fixes have actually come from so far, "
        "not just how many. A rising share of `interpreter_pattern_collision` late in the run would "
        "suggest fixes are papering over collisions rather than resolving them, even if raw coverage "
        "looks flat or improved (see completion.py's criterion #4)."
    )
    lines.append("")
    lines.append("| Design layer | Share |")
    lines.append("|---|---|")
    for tag, pct in histogram.items():
        lines.append(f"| `{tag}` | {pct}% |")
    lines.append("")
    return "\n".join(lines)


def write_checkpoint_report(
    run_id: int,
    checkpoint_n: int,
    outcome_counts_by_phase: dict,
    circuit_breaker_status: dict,
    distinct_fingerprints_seen: int,
    new_fingerprints_this_batch: int,
    clusters: list[Cluster],
    occurrence_threshold_pct: float,
    proposed_fixes: list[ProposedFix],
    gate_results: dict,  # {id(ProposedFix): GateResult} or keyed however the caller tracks it
    needs_human_decision: list[NeedsHumanDecision],
    no_generalized_fix: list[NoGeneralizedFix],
    cumulative_accepted_fixes: list[dict],
) -> Path:
    """Writes checkpoints/greenhouse_run_<run_id>/checkpoint_<NNNN>.md and
    returns its path. Pure function of already-computed inputs — does not
    itself run any checker or query the DB."""
    histogram = compute_design_layer_histogram(cumulative_accepted_fixes)

    sections = [
        f"# Checkpoint {checkpoint_n} — Run {run_id}",
        "",
        "## Batch outcome summary",
        "",
        f"Outcomes are labeled `{_MECHANICALLY_VERIFIED_LABEL}`, never \"success\"/\"clean\" — "
        "a value landed where the extension attempted to put one, not confirmation it's the RIGHT value "
        "(see decisions/0010-verification-is-mechanical-not-semantic.md).",
        "",
        _outcome_table(outcome_counts_by_phase),
        _circuit_breaker_section(circuit_breaker_status),
        _fingerprint_novelty_section(distinct_fingerprints_seen, new_fingerprints_this_batch),
        _clusters_section(clusters, occurrence_threshold_pct),
        "## Proposed fixes",
        "",
    ]

    if not proposed_fixes:
        sections.append("_No fixes proposed this checkpoint._\n")
    else:
        for fix in proposed_fixes:
            gr = gate_results.get(id(fix))
            sections.append(_proposed_fix_section(fix, gr))

    sections.append(_needs_human_decision_section(needs_human_decision))
    sections.append(_no_generalized_fix_section(no_generalized_fix))
    sections.append(_design_layer_histogram_section(histogram))

    out_path = checkpoint_report_path(run_id, checkpoint_n)
    out_path.write_text("\n".join(sections), encoding="utf-8")
    logger.info("Wrote checkpoint report: %s", out_path)
    return out_path
