"""Tier 3 category classifier — LLM fallback for jobs Tiers 1-2 leave empty.

Design locked in decisions/0003-category-classifier-design.md. Must return
empty/no-category rather than force a guess (same "honest null beats
confident wrong answer" rule as decisions/0001). Title-hash caching so
repeated postings across companies/re-polls don't re-classify identical
titles. Callers collect regex/metadata-empty jobs during a poll cycle and
classify them together in one batched call after the fetch completes —
this module does not call the poller loop itself.

`classify_fn` is free-text output from an LLM (or a subagent stand-in), so
its categories aren't guaranteed to be real taxonomy keys — the Jul 24 eval
found a real invented category (`procurement`, should have been
`supply_chain`) and a real key-typo (`health_care` vs the actual
`"health care"` key) in raw Tier 3 output. `classify_batch` validates every
category against `TAXONOMY` and drops anything that doesn't match exactly
— see decisions/0003's "structured-output schema not yet written" gap.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Callable, Iterable

from pollers.filter import _CATEGORY_PATTERNS

logger = logging.getLogger(__name__)

TAXONOMY: tuple[str, ...] = tuple(_CATEGORY_PATTERNS.keys())
_TAXONOMY_SET: frozenset[str] = frozenset(TAXONOMY)

# job_id -> categories, populated by classify_batch(); title_hash -> categories
# cache avoids re-classifying identical titles seen across companies/re-polls.
_title_cache: dict[str, list[str]] = {}


def _title_hash(title: str) -> str:
    return hashlib.sha256(title.strip().lower().encode("utf-8")).hexdigest()


def _validate_categories(job_id: str, categories: list[str]) -> list[str]:
    """Drop any category not exactly in TAXONOMY. Logs what it drops so
    silent invented-category/typo defects (like `procurement` or
    `health_care`) show up in production logs instead of only in a
    one-off eval corpus."""
    valid = [c for c in categories if c in _TAXONOMY_SET]
    dropped = [c for c in categories if c not in _TAXONOMY_SET]
    if dropped:
        logger.warning(
            "Tier 3 returned out-of-taxonomy categories for job %s: %s (dropped)",
            job_id, dropped,
        )
    return valid


def classify_batch(
    jobs: Iterable[dict],
    classify_fn: Callable[[list[dict]], dict[str, list[str]]],
) -> dict[str, list[str]]:
    """Classify a batch of regex/metadata-empty jobs.

    `jobs` — iterable of {"job_id": str, "title": str, "description": str}.
    `classify_fn` — does the actual classification (real LLM call in
    production; a dispatched-subagent stub for this local test run). Takes
    the list of cache-miss jobs, returns {job_id: [categories]}. Must honor
    the empty-list-on-uncertain contract; this module does not second-guess it.

    Returns {job_id: [categories]} for the full input batch, cache hits included.
    """
    jobs = list(jobs)
    results: dict[str, list[str]] = {}
    to_classify: list[dict] = []

    for job in jobs:
        h = _title_hash(job["title"])
        if h in _title_cache:
            results[job["job_id"]] = _title_cache[h]
        else:
            to_classify.append(job)

    if to_classify:
        fresh = classify_fn(to_classify)
        for job in to_classify:
            cats = _validate_categories(job["job_id"], fresh.get(job["job_id"], []))
            results[job["job_id"]] = cats
            _title_cache[_title_hash(job["title"])] = cats

    return results
