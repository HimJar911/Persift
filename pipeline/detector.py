import logging
from typing import Awaitable, Callable

from db import (
    filter_new_ids,
    find_incomplete_ids,
    mark_seen_batch,
    repair_jobs_batch,
    repair_metadata_batch,
)
from pipeline.enricher import enrich

logger = logging.getLogger(__name__)


async def detect_new_jobs(
    jobs: list[dict],
    ats: str,
    pre_insert: Callable[[list[dict]], Awaitable[None]] | None = None,
) -> list[dict]:
    """Return only jobs we haven't seen before — enriched, then persisted.

    Enrichment (JD html→text, company-name derivation) runs BEFORE the insert
    so rows land with real description/company_name/apply_url. The pre-Jul-2026
    pipeline inserted first and handed the enriched dict only to Slack, leaving
    every row empty (fable_audit Area 1). Returned dicts are the enriched ones,
    so downstream consumers need no second enrich().

    pre_insert: optional async callback run on the new raw jobs before
    enrichment (e.g. Jobright apply_url resolution) so its output is persisted.

    Self-healing: polled jobs already in the DB whose row has an empty
    description/company_name/apply_url are repaired from this poll's data.
    At steady state find_incomplete_ids returns nothing, so the extra cost is
    one indexed SELECT per cycle. raw_ats_metadata is backfilled the same way
    on every already-seen job in this poll (repair_metadata_batch no-ops once
    a row already has real data) — catches up rows inserted before a given
    ATS started capturing a field, e.g. Jul 22's Greenhouse 'departments' /
    Lever 'department' capture-gap fixes.
    """
    new_jobs = await filter_new_ids(jobs)

    if pre_insert is not None and new_jobs:
        await pre_insert(new_jobs)

    enriched = [enrich(j) for j in new_jobs]
    await mark_seen_batch(enriched)

    # Repair pass over the already-seen remainder of this poll.
    new_keys = {(j["job_id"], j["ats"]) for j in new_jobs}
    seen_jobs = [j for j in jobs if (j["job_id"], j["ats"]) not in new_keys]
    incomplete = await find_incomplete_ids(seen_jobs)
    if incomplete:
        repairs = [enrich(j) for j in seen_jobs if (j["job_id"], j["ats"]) in incomplete]
        await repair_jobs_batch(repairs)
        logger.info("%s: repaired %d job rows with empty fields", ats, len(repairs))

    if seen_jobs:
        await repair_metadata_batch(seen_jobs)

    if enriched:
        logger.info(
            "%s: %d new jobs detected out of %d total",
            ats, len(enriched), len(jobs),
        )
    else:
        logger.debug("%s: no new jobs (checked %d)", ats, len(jobs))

    return enriched
