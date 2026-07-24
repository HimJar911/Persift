"""One-time backfill: add function/department/experienceLevel/typeOfEmployment
into raw_ats_metadata on existing SmartRecruiters job rows.

Same root cause as scripts/backfill_country.py (which only added 'country'):
these fields are correctly requested and stored by pollers/smartrecruiters.py
going forward, but the ~195K existing rows were captured before that, and
SmartRecruiters' payload-hash skip means a normal poll cycle never reaches
most of them to self-heal. Confirmed live (Jul 23 2026): only 82 of 195,386
rows have the 'function' key at all.

Re-polls every tracked SmartRecruiters company live. Merges via jsonb `||`
so existing keys (including the 'country' this backfill already added) are
preserved, not overwritten. Chunked per decisions/0006.

Run: python -m scripts.backfill_sr_function
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
_CONCURRENCY = 15


def _chunks(items: list, size: int = _CHUNK_SIZE):
    for i in range(0, len(items), size):
        yield items[i:i + size]


async def main() -> None:
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=2, max_size=10)
    try:
        slugs = [r["company_slug"] for r in await pool.fetch(
            "SELECT DISTINCT company_slug FROM jobs WHERE ats='smartrecruiters'"
        )]
        logger.info("SmartRecruiters: %d companies to re-poll for function backfill", len(slugs))

        updates: dict[str, dict] = {}
        sem = asyncio.Semaphore(_CONCURRENCY)
        async with httpx.AsyncClient(timeout=25) as client:
            async def fetch(slug: str) -> None:
                async with sem:
                    offset = 0
                    while True:
                        try:
                            r = await client.get(
                                f"https://api.smartrecruiters.com/v1/companies/{slug}/postings",
                                params={"limit": 100, "offset": offset},
                            )
                            if r.status_code != 200:
                                return
                            data = r.json()
                        except Exception:
                            return
                        content = data.get("content") or []
                        if not content:
                            return
                        for job in content:
                            job_id = str(job.get("id", ""))
                            if not job_id:
                                continue
                            updates[job_id] = {
                                "function": job.get("function"),
                                "department": job.get("department"),
                                "experienceLevel": job.get("experienceLevel"),
                                "typeOfEmployment": job.get("typeOfEmployment"),
                            }
                        offset += 100
                        if offset >= data.get("totalFound", 0):
                            return
            await asyncio.gather(*[fetch(s) for s in slugs])

        logger.info("SmartRecruiters: %d job_ids fetched", len(updates))

        items = list(updates.items())
        applied = 0
        async with pool.acquire() as conn:
            for chunk in _chunks(items):
                await conn.execute(
                    """
                    UPDATE jobs AS j
                    SET raw_ats_metadata = COALESCE(j.raw_ats_metadata, '{}'::jsonb) || c.fields
                    FROM (
                        SELECT unnest($1::text[]) AS job_id,
                               unnest($2::jsonb[]) AS fields
                    ) AS c
                    WHERE j.job_id = c.job_id AND j.ats = 'smartrecruiters'
                    """,
                    [jid for jid, _ in chunk],
                    [json.dumps(fields) for _, fields in chunk],
                )
                applied += len(chunk)
                logger.info("SmartRecruiters function backfill: applied %d/%d", applied, len(items))

        logger.info("SmartRecruiters function backfill complete, %d rows updated", applied)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
