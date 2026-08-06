"""Runs the project's existing regression/parity/replay checkers against a
scratch copy (propose_fix.py's git worktree), pre- and post-fix, per
joyful-sprouting-swan.md's "Checkpoint pass" §3.

Three checks:
    1. check_regressions.js — must exit 0 on the POST-fix scratch copy
       (hard gate: a drafted fix that breaks an existing regression entry
       is never approvable, no judgment call here).
    2. check_js_python_parity.js --json-out=... — run pre- AND post-fix
       against the SAME fixed recorded seed; post must not introduce any
       disagreement absent pre-fix (hard gate on NEW disagreements; an
       existing disagreement the fix doesn't touch is not this fix's
       problem to solve).
    3. replay.py --interpreter interpreter_p14 --report-out ... — run
       pre- AND post-fix; coverage_pct must not decrease (hard gate).
       mismatch_pct/predicted_unknown_pct deltas are reported but NOT
       auto-blocking — a legitimate refinement can shift some "unknown"
       into "mismatch" en route to fully correct, a human judgment call
       per the plan, not something gate.py should silently reject.

Public API:
    GateResult                — pass/fail + full detail for one proposed fix (dataclass)
    run_gate(proposed_fix, scratch_dir, real_repo_dir, fixed_seed) -> GateResult
"""

import dataclasses
import json
import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent

# Recorded once, reused for every pre/post parity comparison in a given
# checkpoint run — per the plan's "fixed recorded seed" requirement. Not
# regenerated per-fix: pre/post must sample the SAME fields to make "no new
# disagreements" a meaningful comparison, and a fixed constant is simpler
# and more auditable than threading a run-specific seed through every call.
DEFAULT_PARITY_SEED = 20260806
DEFAULT_PARITY_SAMPLE_SIZE = 500


@dataclasses.dataclass
class RegressionCheckResult:
    passed: bool
    exit_code: int
    output: str


@dataclasses.dataclass
class ParityCheckResult:
    pre_summary: dict
    post_summary: dict
    new_disagreements: list[dict]
    passed: bool


@dataclasses.dataclass
class ReplayCheckResult:
    pre_report: dict
    post_report: dict
    coverage_delta: float
    mismatch_delta: float
    unknown_delta: float
    passed: bool


@dataclasses.dataclass
class GateResult:
    regression: RegressionCheckResult
    parity: ParityCheckResult
    replay: ReplayCheckResult

    @property
    def passed(self) -> bool:
        # Hard gates only: regression must exit 0, parity must not introduce
        # new disagreements, replay coverage must not drop. mismatch/unknown
        # deltas are surfaced in the report but never block here — per the
        # plan, that's the human's judgment call at approval time, not an
        # automatic pass/fail criterion.
        return self.regression.passed and self.parity.passed and self.replay.passed


def _run_node_script(cwd: Path, script_relpath: str, args: list[str]) -> tuple[int, str]:
    try:
        result = subprocess.run(
            ["node", script_relpath] + args,
            cwd=cwd, capture_output=True, text=True, timeout=600,
        )
        return result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return 1, f"TIMEOUT running {script_relpath}"
    except Exception as exc:
        logger.error("Failed to run %s", script_relpath, exc_info=True)
        return 1, f"EXCEPTION: {exc}"


def _run_check_regressions(repo_dir: Path) -> RegressionCheckResult:
    code, output = _run_node_script(repo_dir, "corpus_analysis/check_regressions.js", [])
    return RegressionCheckResult(passed=(code == 0), exit_code=code, output=output)


def _run_parity_check(repo_dir: Path, out_path: Path, seed: int, sample_size: int) -> dict:
    code, output = _run_node_script(
        repo_dir, "corpus_analysis/check_js_python_parity.js",
        [str(sample_size), str(seed), f"--json-out={out_path}"],
    )
    if not out_path.exists():
        logger.error("Parity checker did not produce %s (exit=%d). Output:\n%s", out_path, code, output)
        return {"sampleSize": 0, "seed": seed, "agree": 0, "total": 0, "disagreements": []}
    return json.loads(out_path.read_text(encoding="utf-8"))


def _diff_parity_disagreements(pre: dict, post: dict) -> list[dict]:
    """Keys present in post but not pre — the plan's "post must not
    introduce new disagreements vs. pre" requirement. A key present in BOTH
    (an existing, untouched disagreement) is explicitly NOT flagged — this
    fix didn't create it, isn't responsible for fixing it, and re-flagging
    every checkpoint would drown the signal that actually matters here."""
    pre_keys = {d["key"] for d in pre.get("disagreements", [])}
    return [d for d in post.get("disagreements", []) if d["key"] not in pre_keys]


def _run_replay(repo_dir: Path, out_path: Path) -> dict:
    # replay.py is designed to run with cwd inside corpus_analysis/ itself
    # (its own module docstring: "Run: python replay.py ..."; BASE =
    # Path(__file__).parent, not a package-relative import) — NOT as
    # `python -m corpus_analysis.replay` from the repo root.
    result = subprocess.run(
        [sys.executable, "replay.py", "--interpreter", "interpreter_p14", "--report-out", str(out_path)],
        cwd=repo_dir / "corpus_analysis", capture_output=True, text=True, timeout=1800,
    )
    if not out_path.exists():
        logger.error(
            "replay.py did not produce %s (exit=%d). stdout:\n%s\nstderr:\n%s",
            out_path, result.returncode, result.stdout, result.stderr,
        )
        return {"coverage_pct": 0.0, "mismatch_pct": 100.0, "predicted_unknown_pct": 100.0}
    return json.loads(out_path.read_text(encoding="utf-8"))


def run_gate(
    scratch_dir: Path,
    real_repo_dir: Path = PROJECT_DIR,
    seed: int = DEFAULT_PARITY_SEED,
    sample_size: int = DEFAULT_PARITY_SAMPLE_SIZE,
    work_dir: Path | None = None,
) -> GateResult:
    """Runs all three checks pre-fix (against real_repo_dir, unmodified)
    and post-fix (against scratch_dir, which propose_fix.py has already
    edited). work_dir is where the pre/post JSON artifacts land — defaults
    to scratch_dir's parent so they're easy to find alongside the scratch
    copy itself, cleaned up together."""
    work_dir = work_dir or scratch_dir.parent
    work_dir.mkdir(parents=True, exist_ok=True)

    # 1. check_regressions.js — POST-fix only. Pre-fix is the real repo's
    # current state, which is by definition already passing (it's what's
    # committed); the only thing worth checking is whether the DRAFTED
    # change breaks it.
    regression = _run_check_regressions(scratch_dir)

    # 2. Parity — pre (real repo) and post (scratch), same fixed seed.
    pre_parity = _run_parity_check(real_repo_dir, work_dir / "parity_pre.json", seed, sample_size)
    post_parity = _run_parity_check(scratch_dir, work_dir / "parity_post.json", seed, sample_size)
    new_disagreements = _diff_parity_disagreements(pre_parity, post_parity)
    parity = ParityCheckResult(
        pre_summary=pre_parity, post_summary=post_parity,
        new_disagreements=new_disagreements, passed=(len(new_disagreements) == 0),
    )

    # 3. Replay — pre (real repo) and post (scratch).
    pre_replay = _run_replay(real_repo_dir, work_dir / "replay_pre.json")
    post_replay = _run_replay(scratch_dir, work_dir / "replay_post.json")
    coverage_delta = post_replay.get("coverage_pct", 0.0) - pre_replay.get("coverage_pct", 0.0)
    mismatch_delta = post_replay.get("mismatch_pct", 0.0) - pre_replay.get("mismatch_pct", 0.0)
    unknown_delta = post_replay.get("predicted_unknown_pct", 0.0) - pre_replay.get("predicted_unknown_pct", 0.0)
    replay = ReplayCheckResult(
        pre_report=pre_replay, post_report=post_replay,
        coverage_delta=round(coverage_delta, 3), mismatch_delta=round(mismatch_delta, 3),
        unknown_delta=round(unknown_delta, 3),
        # Small negative-noise tolerance only, not a real slack allowance:
        # replay.py runs deterministically against the full corpus (no
        # random sampling in run_replay itself), so coverage_pct should be
        # an exact non-decrease in practice — this tolerance exists purely
        # to avoid a float-rounding false failure, not to paper over a real
        # regression.
        passed=(coverage_delta >= -0.01),
    )

    return GateResult(regression=regression, parity=parity, replay=replay)
