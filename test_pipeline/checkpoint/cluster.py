"""Groups failures accumulated since the last checkpoint into candidate bug
classes, per joyful-sprouting-swan.md's "Checkpoint pass" §1.

Primary grouping key is a structural fingerprint — (reason_code,
category_attempted_or_none, autocomplete, id_pattern, role, html_type,
options_hash) — the same structural signals the interpreter's own tiers
trust before label text (autocomplete > id > label > placeholder, per
INTERPRETER_SPEC.md). Label-text similarity is a fallback tiebreaker only,
used to merge fingerprint-adjacent clusters that look like the same
underlying bug phrased differently.

Scope note: this only clusters FIELD-level failures (a job that reached
field-fill attempts and had at least one fail). Jobs with zero field
failures — most commonly timeout/harness_error, which can occur before any
field is ever attempted — produce no clusters here by design; a systemic
streak of those is the circuit breaker's job (test_pipeline/circuit_breaker.py),
not this module's. report.py should surface timeout/harness_error counts
from harness_job_state directly, not expect cluster.py to explain them.

Public API:
    Cluster                — one candidate bug class (dataclass)
    cluster_failures(failure_records, all_attempt_records, jobs_processed_this_batch) -> list[Cluster]
"""

import dataclasses
import logging
import math
import re
from collections import defaultdict

from test_pipeline.failure_log import FieldFailure, JobAttemptRecord, JobFailureRecord

logger = logging.getLogger(__name__)

# Same suffix-stripping convention as corpus_analysis/interpreter_p14.py's
# _tier_id() — reused for consistency, not reinvented, since the whole point
# of clustering on id_pattern (not raw id) is to match the same normalization
# the interpreter itself already trusts (e.g. Greenhouse's
# "question_68457411" per-job-instance ids should cluster as "question_",
# not as N distinct one-off ids).
_ID_TRAILING_DIGITS_RE = re.compile(r"[-_]{1,2}\d+$")


def normalize_id_pattern(field_id: str) -> str:
    if not field_id:
        return ""
    return _ID_TRAILING_DIGITS_RE.sub("", field_id.strip())


@dataclasses.dataclass(frozen=True)
class StructuralFingerprint:
    reason_code: str
    category_attempted: str | None
    autocomplete: str
    id_pattern: str
    role: str
    html_type: str
    options_hash: str

    def as_tuple(self):
        return (
            self.reason_code, self.category_attempted, self.autocomplete,
            self.id_pattern, self.role, self.html_type, self.options_hash,
        )


@dataclasses.dataclass
class ClusterMember:
    job_id: str
    ats: str
    sample_phase: str
    company_name: str
    label: str
    field_failure: FieldFailure


@dataclasses.dataclass
class SuccessExample:
    job_id: str
    ats: str
    sample_phase: str
    label: str
    category: str


@dataclasses.dataclass
class Cluster:
    fingerprint: StructuralFingerprint
    members: list[ClusterMember]
    paired_successes: list[SuccessExample]
    meets_threshold: bool
    occurrence_threshold: int

    @property
    def occurrence_count(self) -> int:
        return len(self.members)

    @property
    def distinct_labels(self) -> list[str]:
        seen = []
        for m in self.members:
            if m.label not in seen:
                seen.append(m.label)
        return seen


def _fingerprint_for_failure(ff: FieldFailure) -> StructuralFingerprint:
    return StructuralFingerprint(
        reason_code=ff.reason_code,
        category_attempted=ff.category_attempted,
        autocomplete=ff.autocomplete or "",
        id_pattern=normalize_id_pattern(ff.id),
        role=ff.role or "",
        html_type=ff.html_type or "",
        options_hash=ff.options_hash or "",
    )


def _normalize_label(label: str) -> str:
    return re.sub(r"\s+", " ", (label or "").strip().lower())


def _label_similarity(a: str, b: str) -> float:
    """Cheap token-overlap similarity (Jaccard on whitespace tokens) — a
    fallback tiebreaker only, per the plan, used to decide whether two
    fingerprint-ADJACENT clusters (same reason_code + category, differing
    only in a field that's often noisy like autocomplete='' vs missing)
    likely represent the same underlying bug. Never used as the primary
    grouping key — two structurally different bugs with similar English
    labels must NOT merge into one diagnosis."""
    ta = set(_normalize_label(a).split())
    tb = set(_normalize_label(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _occurrence_threshold(jobs_processed_this_batch: int) -> int:
    """max(3, ceil(0.02 * jobs_processed_this_batch)) — proportional, not a
    fixed absolute count, per the plan. 2% is a stated, visible parameter
    (returned here, surfaced by report.py) not a silently hardcoded magic
    number."""
    return max(3, math.ceil(0.02 * jobs_processed_this_batch))


def _find_paired_successes(
    fingerprint: StructuralFingerprint,
    all_attempt_records: list[JobAttemptRecord],
    limit: int = 5,
) -> list[SuccessExample]:
    """Pulls the nearest successful fills sharing the same reason-code-
    adjacent structural family — same html_type/role, same category
    attempted, but landed=True — from the run's FULL job history (not just
    this batch), per the plan. Answers "what's different about the forms
    that failed vs. the ones that didn't" without leaving that diffing work
    to the human reading the report."""
    examples: list[SuccessExample] = []
    for record in all_attempt_records:
        for a in record.attempts:
            if not a.landed:
                continue
            if a.category != (fingerprint.category_attempted or a.category):
                continue
            same_family = (
                a.html_type == fingerprint.html_type
                and a.role == fingerprint.role
                and normalize_id_pattern(a.id) == fingerprint.id_pattern
            )
            if same_family:
                examples.append(SuccessExample(
                    job_id=record.job_id, ats=record.ats, sample_phase=record.sample_phase,
                    label=a.label, category=a.category,
                ))
                if len(examples) >= limit:
                    return examples
    return examples


def cluster_failures(
    failure_records: list[JobFailureRecord],
    all_attempt_records: list[JobAttemptRecord],
    jobs_processed_this_batch: int,
) -> list[Cluster]:
    """Groups every FieldFailure across failure_records (the batch
    accumulated since the last checkpoint) by structural fingerprint, pairs
    each cluster meeting the occurrence threshold with nearby successes from
    the run's full history, and returns ALL clusters (including
    sub-threshold ones — the plan wants those shown in the report as "not
    yet a class", not silently dropped)."""
    threshold = _occurrence_threshold(jobs_processed_this_batch)

    grouped: dict[StructuralFingerprint, list[ClusterMember]] = defaultdict(list)
    for record in failure_records:
        for ff in record.field_failures:
            fp = _fingerprint_for_failure(ff)
            grouped[fp].append(ClusterMember(
                job_id=record.job_id, ats=record.ats, sample_phase=record.sample_phase,
                company_name=record.company_name, label=ff.label, field_failure=ff,
            ))

    # Fallback tiebreaker merge pass: two fingerprint-distinct groups that
    # differ only in id_pattern/autocomplete (both often legitimately empty
    # or noisy) but share reason_code + category_attempted + high label
    # similarity across their member sets are likely the same underlying
    # bug phrased differently. Merged conservatively — only when average
    # pairwise label similarity across a sample is high, not on any single
    # label match, since a false merge (two real distinct bugs collapsed
    # into one) is a worse failure mode than an unmerged near-duplicate
    # (which just shows up as two smaller clusters in the report instead
    # of one, still visible, still actionable).
    fingerprints = list(grouped.keys())
    merged_into: dict[StructuralFingerprint, StructuralFingerprint] = {fp: fp for fp in fingerprints}

    for i, fp_a in enumerate(fingerprints):
        for fp_b in fingerprints[i + 1:]:
            if merged_into[fp_a] == merged_into[fp_b]:
                continue
            if fp_a.reason_code != fp_b.reason_code:
                continue
            if fp_a.category_attempted != fp_b.category_attempted:
                continue
            if fp_a.role != fp_b.role or fp_a.html_type != fp_b.html_type:
                continue
            # Only consider merging when id_pattern/autocomplete are the
            # differentiator (both weak/empty signals here), never when
            # they meaningfully differ.
            if fp_a.id_pattern and fp_b.id_pattern and fp_a.id_pattern != fp_b.id_pattern:
                continue

            labels_a = [m.label for m in grouped[fp_a]][:5]
            labels_b = [m.label for m in grouped[fp_b]][:5]
            if not labels_a or not labels_b:
                continue
            sims = [_label_similarity(la, lb) for la in labels_a for lb in labels_b]
            avg_sim = sum(sims) / len(sims)
            if avg_sim >= 0.6:
                root_a, root_b = merged_into[fp_a], merged_into[fp_b]
                for fp in fingerprints:
                    if merged_into[fp] == root_b:
                        merged_into[fp] = root_a

    final_groups: dict[StructuralFingerprint, list[ClusterMember]] = defaultdict(list)
    for fp, members in grouped.items():
        final_groups[merged_into[fp]].extend(members)

    clusters = []
    for fp, members in final_groups.items():
        meets = len(members) >= threshold
        paired = _find_paired_successes(fp, all_attempt_records) if meets else []
        clusters.append(Cluster(
            fingerprint=fp, members=members, paired_successes=paired,
            meets_threshold=meets, occurrence_threshold=threshold,
        ))

    clusters.sort(key=lambda c: -c.occurrence_count)
    return clusters
