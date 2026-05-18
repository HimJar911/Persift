import logging

from db import filter_new_ids, mark_seen_batch

logger = logging.getLogger(__name__)


async def detect_new_jobs(jobs: list[dict], ats: str) -> list[dict]:
    """Return only jobs we haven't seen before and mark them as seen.

    Diffing is done in SQL — we send the candidate IDs to the DB and it
    returns only the ones that don't exist yet.  Then we batch-insert all
    new jobs in a single transaction.
    """
    candidate_ids = [j["job_id"] for j in jobs]
    new_ids = await filter_new_ids(candidate_ids, ats)

    new_jobs = [j for j in jobs if j["job_id"] in new_ids]

    # Batch-insert in one transaction
    await mark_seen_batch(new_jobs)

    if new_jobs:
        logger.info(
            "%s: %d new jobs detected out of %d total",
            ats, len(new_jobs), len(jobs),
        )
    else:
        logger.debug("%s: no new jobs (checked %d)", ats, len(jobs))

    return new_jobs
