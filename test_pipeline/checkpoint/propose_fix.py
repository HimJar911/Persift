"""Drafts fix proposals for clusters that meet the occurrence threshold,
against a SCRATCH copy of the repo (git worktree) — never the real files
directly. Per joyful-sprouting-swan.md's "Checkpoint pass" §2 and the plan's
hard invariant.

**Scope, deliberately narrow for this first build** (confirmed with the
user 2026-08-06, not a unilateral call): the only kind of pattern
refinement propose_fix.py may autonomously draft is a NEGATIVE GUARD
addition — appending one regex to an EXISTING capability's `neg` list in
BOTH extension/filler_utils.js's FIELD_PATTERNS and
corpus_analysis/interpreter_p14.py's _FIELD_PATTERNS. This is the shape of
7 of the 12 real regression entries in interpreter_regressions.json today
(a category's bare pattern stealing fields that mention an excludable
term). Adding a new `patterns` entry, a new category, an id_pattern rule,
or anything else is explicitly OUT of scope here and always produces
"needs_human_decision" instead — those are real capability/architecture
decisions, not narrowing refinements, and get it wrong in the wrong
direction (missing real fields) rather than the comparatively safer wrong
direction (a guard that's too broad, caught by gate.py's regression check).

**Hard invariant** (from the plan, non-negotiable): only
extension/filler_utils.js and corpus_analysis/interpreter_p14.py may be
autonomously drafted. NEVER corpus_analysis/category_mapping.py,
corpus_analysis/taxonomy_v1.py, cluster_decisions_v2.json/
oc_compact_full_v2.json, or extension/consent_policy.js.

Public API:
    ProposedFix               — one drafted fix (dataclass)
    NeedsHumanDecision         — a cluster that looks like a new-concept candidate (dataclass)
    NoGeneralizedFix           — a cluster reviewed with no class-level fix found (dataclass)
    propose_fixes_for_clusters(clusters, scratch_repo_dir) -> list[ProposedFix | NeedsHumanDecision | NoGeneralizedFix]
"""

import dataclasses
import logging
import re
import subprocess
from pathlib import Path

from test_pipeline.checkpoint.cluster import Cluster

logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent

# The only files propose_fix.py may ever write to (in a scratch copy).
_ALLOWED_EDIT_FILES = {
    "extension/filler_utils.js",
    "corpus_analysis/interpreter_p14.py",
}

# Never touched, autonomously or otherwise, by this module — restated here
# (not just in the docstring) so a future refactor that adds a new file-edit
# path has to consciously bypass this constant, not just forget a comment.
_FORBIDDEN_FILES = {
    "corpus_analysis/category_mapping.py",
    "corpus_analysis/taxonomy_v1.py",
    "corpus_analysis/cluster_decisions_v2.json",
    "corpus_analysis/oc_compact_full_v2.json",
    "extension/consent_policy.js",
}

# Fixed taxonomy of design-layer tags, per the plan — every accepted fix
# must carry exactly one of these, stored in the regression entry's note.
DESIGN_LAYER_TAGS = {
    "interpreter_pattern_collision", "fill_mechanics", "verification_gap",
    "policy_gap", "capability_gap", "browser_interaction", "harness_infra", "other",
}

# reason_codes this module knows how to reason about as "existing category
# wrongly matched something it shouldn't have" — the negative-guard shape.
# Every other reason_code (DOM_LISTBOX_NEVER_OPENED, INTERACTION_NO_OPTION_MATCHED
# without a clear over-match story, etc.) is fill_mechanics/browser_interaction
# territory, not a label-pattern fix, and is always routed to
# needs_human_decision or no_generalized_fix instead.
_GUARD_CANDIDATE_REASON_CODES = {"CLASSIFICATION_NO_MATCH"}


@dataclasses.dataclass
class ProposedFix:
    cluster: Cluster
    category: str
    guard_term: str
    guard_regex_js: str
    guard_regex_py: str
    design_layer_tag: str
    rationale: str
    negative_guard_check_passed: bool
    negative_guard_conflicts: list[str]
    diff_js: str
    diff_py: str
    regression_entry: dict


@dataclasses.dataclass
class NeedsHumanDecision:
    cluster: Cluster
    reason: str


@dataclasses.dataclass
class NoGeneralizedFix:
    cluster: Cluster
    reason: str


def _tokenize(label: str) -> set[str]:
    return set(re.findall(r"[a-z]{3,}", (label or "").lower()))


def _existing_neg_terms(scratch_dir: Path, category: str) -> set[str]:
    """Reads the category's CURRENT neg list (Python side, source of truth
    for this lookup since both files are kept in lockstep) so
    _find_distinguishing_term never proposes re-adding a term that's
    already there. Real bug caught while testing this module: without this
    check, a cluster whose labels all shared an already-guarded term (e.g.
    'newsletter', already excluded from `email`) could have that term
    picked over a genuinely new one, silently producing a duplicate/no-op
    guard instead of a real fix."""
    py_path = scratch_dir / "corpus_analysis" / "interpreter_p14.py"
    try:
        py_source = py_path.read_text(encoding="utf-8")
    except Exception:
        return set()
    span = _py_field_patterns_neg_span(py_source, category)
    if span is None:
        return set()
    neg_block = py_source[span[0]:span[1]]
    # Extract the literal words inside each r"..." regex in the neg list —
    # a cheap approximation (not a real regex parser) but sufficient for
    # spotting "this exact plain word is already a guard term."
    return {m.lower() for m in re.findall(r'r"([a-zA-Z ]+)"', neg_block)}


def _find_distinguishing_term(cluster: Cluster, already_guarded: set[str] = frozenset()) -> str | None:
    """Looks for a word or short phrase present in EVERY failing member's
    label but absent from every paired-success label — the signature of "a
    category's pattern is too broad, and this term reliably marks the
    fields it shouldn't match." Deliberately conservative: returns None
    (no candidate) unless the signal is clean across the whole cluster, not
    just a majority — a partial signal here means "not confident enough to
    auto-draft," which routes to needs_human_decision, not a bad guess."""
    member_labels = [m.label for m in cluster.members if m.label]
    if len(member_labels) < 2:
        return None

    token_sets = [_tokenize(l) for l in member_labels]
    common = set.intersection(*token_sets) if token_sets else set()
    if not common:
        return None

    success_labels = [s.label for s in cluster.paired_successes if s.label]
    success_tokens: set[str] = set()
    for l in success_labels:
        success_tokens |= _tokenize(l)

    candidates = common - success_tokens - already_guarded
    # Filter out near-universal stopword-ish tokens that would make a
    # guard far too broad even if they happen to be common across this
    # cluster's small sample.
    _STOP = {"the", "you", "your", "are", "and", "for", "this", "that", "will",
              "have", "with", "please", "any", "our", "what", "when", "does"}
    candidates -= _STOP

    if not candidates:
        return None
    # Prefer the shortest candidate — a shorter, more specific-looking term
    # is less likely to be an accidental co-occurrence; longer common words
    # across a small sample are more likely coincidence in a 3-5 member
    # cluster. This is a heuristic, not a guarantee — gate.py's regression
    # check is the real safety net, not this ranking.
    return sorted(candidates, key=len)[0]


def _js_field_patterns_neg_span(js_source: str, category: str) -> tuple[int, int] | None:
    """Finds the character span of `category`'s `neg: [...]` array literal
    in filler_utils.js's FIELD_PATTERNS block, or None if the category has
    no neg list yet (adding one where none exists is a bigger structural
    change than appending to an existing list — out of scope, routes to
    needs_human_decision)."""
    cat_pattern = re.compile(r"\b" + re.escape(category) + r":\s*\{")
    m = cat_pattern.search(js_source)
    if not m:
        return None
    block_start = m.end()
    depth = 1
    i = block_start
    while i < len(js_source) and depth > 0:
        if js_source[i] == "{":
            depth += 1
        elif js_source[i] == "}":
            depth -= 1
        i += 1
    block_end = i
    block = js_source[block_start:block_end]

    neg_match = re.search(r"neg:\s*\[", block)
    if not neg_match:
        return None
    neg_array_start = block_start + neg_match.end()
    depth = 1
    j = neg_array_start
    while j < len(js_source) and depth > 0:
        if js_source[j] == "[":
            depth += 1
        elif js_source[j] == "]":
            depth -= 1
        j += 1
    neg_array_end = j - 1  # position of closing ']'
    return neg_array_start, neg_array_end


def _py_field_patterns_neg_span(py_source: str, category: str) -> tuple[int, int] | None:
    cat_pattern = re.compile(r'"' + re.escape(category) + r'":\s*\{')
    m = cat_pattern.search(py_source)
    if not m:
        return None
    block_start = m.end()
    depth = 1
    i = block_start
    while i < len(py_source) and depth > 0:
        if py_source[i] == "{":
            depth += 1
        elif py_source[i] == "}":
            depth -= 1
        i += 1
    block_end = i
    block = py_source[block_start:block_end]

    neg_match = re.search(r'"neg":\s*\[', block)
    if not neg_match:
        return None
    neg_array_start = block_start + neg_match.end()
    depth = 1
    j = neg_array_start
    while j < len(py_source) and depth > 0:
        if py_source[j] == "[":
            depth += 1
        elif py_source[j] == "]":
            depth -= 1
        j += 1
    neg_array_end = j - 1
    return neg_array_start, neg_array_end


def _draft_guard_edit(scratch_dir: Path, category: str, guard_term: str) -> tuple[str, str, str, str] | None:
    """Inserts a new negative-guard regex into both FIELD_PATTERNS's neg
    list for `category`. Returns (diff_js, diff_py, regex_js, regex_py), or
    None if either file's neg list couldn't be located (category has no
    neg list yet, or the block structure doesn't match what's expected —
    fails closed to "can't draft this," not a guess)."""
    js_path = scratch_dir / "extension" / "filler_utils.js"
    py_path = scratch_dir / "corpus_analysis" / "interpreter_p14.py"

    js_source = js_path.read_text(encoding="utf-8")
    py_source = py_path.read_text(encoding="utf-8")

    js_span = _js_field_patterns_neg_span(js_source, category)
    py_span = _py_field_patterns_neg_span(py_source, category)
    if js_span is None or py_span is None:
        return None

    # guard_term is always a plain lowercase word from _tokenize's
    # [a-z]{3,} pattern, so no regex-metacharacter escaping is needed for
    # either the JS literal or the Python raw string.
    regex_js = f"/{guard_term}/i"
    regex_py = f'r"{guard_term}"'

    js_start, js_end = js_span
    # Insert right before the closing bracket, adding a leading comma+space
    # only if the neg array is already non-empty.
    existing_neg = js_source[js_start:js_end].strip()
    insertion_js = (f", {regex_js}" if existing_neg else regex_js)
    new_js_source = js_source[:js_end] + insertion_js + js_source[js_end:]

    existing_neg_py = py_source[py_span[0]:py_span[1]].strip()
    insertion_py = (f", {regex_py}" if existing_neg_py else regex_py)
    new_py_source = py_source[:py_span[1]] + insertion_py + py_source[py_span[1]:]

    js_path.write_text(new_js_source, encoding="utf-8")
    py_path.write_text(new_py_source, encoding="utf-8")

    diff_js = _git_diff(scratch_dir, "extension/filler_utils.js")
    diff_py = _git_diff(scratch_dir, "corpus_analysis/interpreter_p14.py")

    return diff_js, diff_py, regex_js, regex_py


def _git_diff(scratch_dir: Path, relpath: str) -> str:
    try:
        out = subprocess.run(
            ["git", "diff", "--", relpath], cwd=scratch_dir,
            capture_output=True, text=True, check=True,
        )
        return out.stdout
    except Exception:
        logger.warning("git diff failed for %s", relpath, exc_info=True)
        return ""


def _check_no_regression_conflicts(scratch_dir: Path, guard_regex_py: str, category: str) -> tuple[bool, list[str]]:
    """Runs the drafted pattern against every EXISTING regression entry's
    label to confirm the new guard doesn't accidentally exclude a label
    that's supposed to correctly resolve to `category` — an automated
    version of FORM_ENGINE_DESIGN.md §1's manual negative-guard check.
    Returns (passed, conflicting_labels)."""
    import json
    regressions_path = scratch_dir / "corpus_analysis" / "interpreter_regressions.json"
    try:
        entries = json.loads(regressions_path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Could not read interpreter_regressions.json for guardrail check", exc_info=True)
        return False, ["<could not read interpreter_regressions.json>"]

    term = guard_regex_py.strip('r"')
    try:
        pattern = re.compile(term, re.I)
    except re.error:
        return False, [f"<invalid regex: {term}>"]

    conflicts = []
    for entry in entries:
        if entry.get("expected_capability") == category and pattern.search(entry.get("label", "")):
            conflicts.append(entry["label"])
    return (len(conflicts) == 0), conflicts


# Files gate.py's checkers need to read but that are NOT git-tracked
# (corpus_analysis/oc_compact_full_v2.json is .gitignore'd — 258MB, exceeds
# GitHub's 100MB limit, "regenerable... not source"). A fresh git worktree
# has no copy of these at all, so check_js_python_parity.js fails outright
# with FileNotFoundError when run against one (confirmed live while testing
# the --json-out flag). Never modified by any drafted fix, so a symlink
# back to the real repo's copy is correct and avoids a 258MB copy per
# checkpoint.
_SYMLINK_INTO_SCRATCH = [
    "corpus_analysis/oc_compact_full_v2.json",
]


def _create_scratch_worktree(run_id: int, checkpoint_n: int) -> Path:
    scratch_dir = PROJECT_DIR / "test_pipeline_scratch" / f"run_{run_id}_checkpoint_{checkpoint_n}"
    if scratch_dir.exists():
        subprocess.run(["git", "worktree", "remove", "--force", str(scratch_dir)], cwd=PROJECT_DIR, capture_output=True)
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(scratch_dir), "HEAD"],
        cwd=PROJECT_DIR, check=True, capture_output=True, text=True,
    )

    for relpath in _SYMLINK_INTO_SCRATCH:
        real_path = PROJECT_DIR / relpath
        link_path = scratch_dir / relpath
        if not real_path.exists():
            logger.warning("Cannot symlink %s into scratch worktree — source doesn't exist locally.", relpath)
            continue
        try:
            if link_path.exists() or link_path.is_symlink():
                link_path.unlink()
            link_path.symlink_to(real_path)
        except OSError:
            logger.warning(
                "Could not symlink %s into scratch worktree (Windows may need admin/dev-mode for "
                "symlinks) — falling back to a copy.", relpath, exc_info=True,
            )
            import shutil
            shutil.copy2(real_path, link_path)

    return scratch_dir


def cleanup_scratch_worktree(scratch_dir: Path) -> None:
    try:
        subprocess.run(["git", "worktree", "remove", "--force", str(scratch_dir)], cwd=PROJECT_DIR, check=True, capture_output=True)
    except Exception:
        logger.warning("Could not remove scratch worktree %s", scratch_dir, exc_info=True)


def propose_fix_for_cluster(cluster: Cluster, scratch_dir: Path):
    """Returns a ProposedFix, NeedsHumanDecision, or NoGeneralizedFix for
    one cluster. Never raises on a cluster it can't confidently handle —
    that's what NoGeneralizedFix/NeedsHumanDecision are for."""
    fp = cluster.fingerprint

    if fp.reason_code not in _GUARD_CANDIDATE_REASON_CODES:
        return NoGeneralizedFix(
            cluster=cluster,
            reason=(
                f"reason_code={fp.reason_code!r} is not in this build's guard-candidate "
                f"scope ({_GUARD_CANDIDATE_REASON_CODES}) — likely fill_mechanics/"
                f"browser_interaction territory, not a label-pattern issue. Needs manual "
                f"review, not auto-draftable in this scope."
            ),
        )

    if not fp.category_attempted:
        return NeedsHumanDecision(
            cluster=cluster,
            reason=(
                "CLASSIFICATION_NO_MATCH with no category_attempted at all — this is a "
                "genuinely unclassified field, which is either a missing POSITIVE pattern "
                "(out of this build's guard-only scope) or a real capability gap. Needs a "
                "human decision on whether this is a new category/capability."
            ),
        )

    category = fp.category_attempted.split("__")[0] if "__" in fp.category_attempted else fp.category_attempted

    already_guarded = _existing_neg_terms(scratch_dir, category)
    guard_term = _find_distinguishing_term(cluster, already_guarded)
    if guard_term is None:
        return NoGeneralizedFix(
            cluster=cluster,
            reason=(
                f"No clean distinguishing term found across this cluster's {cluster.occurrence_count} "
                f"member labels that's absent from paired successes — looks like company-specific "
                f"phrasing variance, not a single generalizable pattern gap."
            ),
        )

    drafted = _draft_guard_edit(scratch_dir, category, guard_term)
    if drafted is None:
        return NeedsHumanDecision(
            cluster=cluster,
            reason=(
                f"Category {category!r} has no existing `neg` list in FIELD_PATTERNS/_FIELD_PATTERNS "
                f"(or its block structure didn't parse as expected) — adding a NEW neg list where none "
                f"exists is a bigger structural change than this build's narrow append-only guard scope."
            ),
        )
    diff_js, diff_py, regex_js, regex_py = drafted

    passed, conflicts = _check_no_regression_conflicts(scratch_dir, regex_py, category)

    regression_entry = {
        "label": cluster.members[0].label,
        "expected_capability": None,  # deliberately blank — this cluster is about EXCLUDING
                                        # this label from `category`, not asserting what it
                                        # should resolve to instead; a human fills this in if
                                        # the fix is approved, once the right capability is known.
        "source": f"self_healing_harness_cluster_{fp.reason_code}",
        "note": (
            f"Auto-drafted negative guard: {category!r} was matching labels containing "
            f"{guard_term!r} (e.g. {cluster.members[0].label[:80]!r}), {cluster.occurrence_count} "
            f"occurrences in this batch. design_layer_tag=interpreter_pattern_collision."
        ),
    }

    return ProposedFix(
        cluster=cluster, category=category, guard_term=guard_term,
        guard_regex_js=regex_js, guard_regex_py=regex_py,
        design_layer_tag="interpreter_pattern_collision",
        rationale=(
            f"{cluster.occurrence_count} failures share reason_code={fp.reason_code!r}, "
            f"category_attempted={fp.category_attempted!r}, and every member label contains "
            f"{guard_term!r} while zero paired-success labels do — the classic shape of an "
            f"over-broad positive pattern needing a negative guard, same shape as 7 of the "
            f"12 real fixes already in interpreter_regressions.json."
        ),
        negative_guard_check_passed=passed,
        negative_guard_conflicts=conflicts,
        diff_js=diff_js, diff_py=diff_py,
        regression_entry=regression_entry,
    )


def propose_fixes_for_clusters(clusters: list[Cluster], run_id: int, checkpoint_n: int):
    """For every cluster meeting threshold, drafts a fix against a shared
    scratch worktree (one per checkpoint, cleaned up by the caller after
    gate.py has run against it). Sub-threshold clusters are not passed a
    fix proposal at all — report.py shows them separately as "not yet a
    class." Returns (results, scratch_dir) — caller owns scratch_dir's
    lifecycle (gate.py runs against it next, then it's cleaned up)."""
    threshold_clusters = [c for c in clusters if c.meets_threshold]
    if not threshold_clusters:
        return [], None

    scratch_dir = _create_scratch_worktree(run_id, checkpoint_n)
    results = []
    for cluster in threshold_clusters:
        try:
            results.append(propose_fix_for_cluster(cluster, scratch_dir))
        except Exception:
            logger.error("propose_fix_for_cluster raised for cluster %s — treating as no_generalized_fix.",
                         cluster.fingerprint, exc_info=True)
            results.append(NoGeneralizedFix(
                cluster=cluster,
                reason="propose_fix_for_cluster raised an exception — see harness log. "
                       "Treated as no-fix-drafted rather than silently skipped.",
            ))
    return results, scratch_dir
