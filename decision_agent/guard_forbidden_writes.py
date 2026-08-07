"""Mechanical backstop for the decision agent's hard file-write ceiling.

The agent's briefing prompt (prompts.py's _HARD_CEILING) instructs it to
NEVER directly write to the 4 forbidden files -- but that's an instruction,
not an enforced constraint, and the agent runs under
--permission-mode bypassPermissions (no interactive approval gate) because
there's no human present to approve tool calls overnight. Prompt
instructions alone are not a real safety boundary against a reasoning
failure or prompt injection (e.g. a malicious/confusing checkpoint report
crafted to look like project docs), so this module is the actual
enforcement point: after every `claude -p` turn that might have committed
something, runner.py calls check_and_revert_forbidden_writes() to inspect
what actually landed in git and revert it if it touched a forbidden path.

Public API:
    FORBIDDEN_PATHS               -- the 4 paths, relative to repo root
    check_and_revert_forbidden_writes(repo_dir, commits_before, commits_after) -> list[str]
        Reverts (via `git revert --no-edit`) any commit in the new range
        that touched a forbidden path. Returns the list of reverted SHAs.
        Never raises on a clean range (no forbidden touches) -- returns [].
"""

import logging
import subprocess

logger = logging.getLogger(__name__)

# Mirrors orchestrate.py's own hard ceiling exactly (propose_fix.py can
# never write these directly either) -- kept as a literal list here rather
# than importing from orchestrate.py so this guard has zero dependency on
# the pipeline code it's checking, per "the checker shouldn't trust the
# thing it's checking."
FORBIDDEN_PATHS = (
    "pollers/filter.py",
    "corpus_analysis/oc_compact_full_v2.json",
    "corpus_analysis/cluster_decisions_v2.json",
    "extension/consent_policy.js",
)


def _commits_between(repo_dir: str, before_sha: str, after_sha: str) -> list[str]:
    if before_sha == after_sha:
        return []
    proc = subprocess.run(
        ["git", "rev-list", f"{before_sha}..{after_sha}"],
        cwd=repo_dir, capture_output=True, text=True, check=True,
    )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _commit_touches_forbidden_path(repo_dir: str, sha: str) -> list[str]:
    proc = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", sha],
        cwd=repo_dir, capture_output=True, text=True, check=True,
    )
    changed = set(line.strip() for line in proc.stdout.splitlines() if line.strip())
    return [p for p in FORBIDDEN_PATHS if p in changed]


def check_and_revert_forbidden_writes(repo_dir: str, commits_before: str, commits_after: str) -> list[str]:
    """commits_before/commits_after are HEAD SHAs captured immediately
    before and after a claude session turn ran. Walks every commit in that
    range (newest-last from rev-list's default order, so revert oldest-
    forbidden-commit-first to avoid revert conflicts on later legitimate
    commits) and reverts any that touched a forbidden path. Logs loudly --
    this should never fire in normal operation, and if it does, it's worth
    a human noticing in the log even though the repo self-heals via revert."""
    commits = _commits_between(repo_dir, commits_before, commits_after)
    reverted = []
    # rev-list default order is newest-first; revert oldest-first so a
    # later legitimate commit that touched unrelated files doesn't create
    # a spurious conflict against an earlier revert.
    for sha in reversed(commits):
        hits = _commit_touches_forbidden_path(repo_dir, sha)
        if not hits:
            continue
        logger.error(
            "SECURITY: decision agent commit %s touched forbidden path(s) %s -- reverting.",
            sha[:8], hits,
        )
        subprocess.run(
            ["git", "revert", "--no-edit", sha],
            cwd=repo_dir, capture_output=True, text=True, check=True,
        )
        reverted.append(sha)
    if reverted:
        logger.error(
            "Reverted %d commit(s) for forbidden-path writes. This should never happen under normal "
            "operation -- investigate the checkpoint context that led to it.", len(reverted),
        )
    return reverted
