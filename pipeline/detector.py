import logging

from db import filter_new_ids, mark_seen_batch

logger = logging.getLogger(__name__)


async def detect_new_jobs(jobs: list[dict], ats: str) -> list[dict]:
    """Return only jobs we haven't seen before and mark them as seen."""
    new_jobs = await filter_new_ids(jobs)
    await mark_seen_batch(new_jobs)

    if new_jobs:
        logger.info(
            "%s: %d new jobs detected out of %d total",
            ats, len(new_jobs), len(jobs),
        )
    else:
        logger.debug("%s: no new jobs (checked %d)", ats, len(jobs))

    return new_jobs
