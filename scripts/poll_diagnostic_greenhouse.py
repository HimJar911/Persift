"""One-shot diagnostic: poll every active Greenhouse company slug and log the
outcome of each attempt to company_poll_log (migration 021), without touching
the jobs table or the live pipeline's dedup/notify path.

Answers: of the 2,127 seeded Greenhouse slugs, how many actually respond with
jobs vs 404/429/5xx/timeout/connection-error vs respond fine but have zero
current intern postings? Run once, then query company_poll_log for the
breakdown (see the summary this script prints at the end).

Usage:
    python scripts/poll_diagnostic_greenhouse.py
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import close_db, get_pool, init_db
from pollers.greenhouse import poll_greenhouse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    await init_db()
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT slug FROM companies WHERE ats = 'greenhouse' AND is_active = TRUE"
            )
        slugs = [r["slug"] for r in rows]
        logger.info("Polling %d active Greenhouse companies (log-only, no jobs table writes)", len(slugs))

        matched_jobs = await poll_greenhouse(slugs)
        logger.info("Poll pass complete — %d matching (intern-role) jobs found across all companies", len(matched_jobs))

        async with pool.acquire() as conn:
            summary = await conn.fetch(
                """
                SELECT outcome, COUNT(*) AS n, COALESCE(SUM(job_count), 0) AS total_jobs
                FROM company_poll_log
                WHERE ats = 'greenhouse' AND polled_at > NOW() - INTERVAL '1 hour'
                GROUP BY outcome
                ORDER BY n DESC
                """
            )
        print("\n=== company_poll_log summary (this run) ===")
        for r in summary:
            print(f"  {r['outcome']:<20} {r['n']:>5} companies   {r['total_jobs']:>6} total jobs")
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
