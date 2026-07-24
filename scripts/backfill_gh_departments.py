"""One-time backfill: add departments[] into raw_ats_metadata on existing
Greenhouse job rows.

Confirmed live (Jul 23 2026 census, 361/367 reachable companies, 41,442
jobs): departments[] is populated on 99.8% of live Greenhouse jobs and
carries real, recurring, cross-company vocabulary (Engineering/107
companies, Sales/89, Finance/104, Marketing/103, etc.) — a much stronger
signal than the category_metadata custom field (only 26% coverage, mostly
single-company vocabulary). The poller already stores departments[] going
forward (Jul 22 capture-gap fix per STATE.md); this backfill catches up the
~195K existing rows that predate that fix and that SmartRecruiters-style
hash-skip logic prevents from ever self-healing on a normal poll cycle.

Merges via jsonb `||` so existing keys (metadata, employment_type, etc.
from the Jul 23 gh_metadata backfill) are preserved. Chunked per
decisions/0006.

Run: python -m scripts.backfill_gh_departments
"""

import asyncio
import json
import logging
import os

import asyncpg
import httpx
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_CHUNK_SIZE = 2000
_CONCURRENCY = 30


def _chunks(items: list, size: int = _CHUNK_SIZE):
    for i in range(0, len(items), size):
        yield items[i:i + size]


async def main() -> None:
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=2, max_size=10)
    try:
        slugs = [r["company_slug"] for r in await pool.fetch(
            "SELECT DISTINCT company_slug FROM jobs WHERE ats='greenhouse'"
        )]
        logger.info("Greenhouse: %d companies to re-poll for departments backfill", len(slugs))

        updates: dict[str, list] = {}
        sem = asyncio.Semaphore(_CONCURRENCY)
        async with httpx.AsyncClient(timeout=25) as client:
            async def fetch(slug: str) -> None:
                async with sem:
                    try:
                        r = await client.get(
                            f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
                            params={"content": "true"},
                        )
                        if r.status_code != 200:
                            return
                        data = r.json()
                    except Exception:
                        return
                for job in data.get("jobs", []):
                    job_id = str(job.get("id", ""))
                    depts = job.get("departments")
                    if not job_id or not depts:
                        continue
                    updates[job_id] = depts
            await asyncio.gather(*[fetch(s) for s in slugs])

        logger.info("Greenhouse: %d job_ids with departments fetched", len(updates))

        items = list(updates.items())
        applied = 0
        async with pool.acquire() as conn:
            for chunk in _chunks(items):
                await conn.execute(
                    """
                    UPDATE jobs AS j
                    SET raw_ats_metadata = COALESCE(j.raw_ats_metadata, '{}'::jsonb)
                        || jsonb_build_object('departments', c.departments)
                    FROM (
                        SELECT unnest($1::text[]) AS job_id,
                               unnest($2::jsonb[]) AS departments
                    ) AS c
                    WHERE j.job_id = c.job_id AND j.ats = 'greenhouse'
                    """,
                    [jid for jid, _ in chunk],
                    [json.dumps(depts) for _, depts in chunk],
                )
                applied += len(chunk)
                logger.info("Greenhouse departments backfill: applied %d/%d", applied, len(items))

        logger.info("Greenhouse departments backfill complete, %d rows updated", applied)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
