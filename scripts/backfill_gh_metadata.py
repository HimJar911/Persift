"""One-time backfill: parse Greenhouse's metadata[] into the normalized
employment_type/workplace_type/experience_level/salary_range/
category_metadata fields (pollers/gh_metadata.py) on existing job rows.

Same pattern as scripts/backfill_country.py: merges new keys into whatever
raw_ats_metadata already exists via Postgres's jsonb `||` operator, rather
than db.repair_metadata_batch (which only fills NULL/'{}' rows and would
skip everything here, since every Greenhouse row already has metadata/
departments captured).

Re-polls each tracked Greenhouse company live. Chunked per decisions/0006.

Run: python -m scripts.backfill_gh_metadata
"""

import asyncio
import json
import logging
import os

import asyncpg
import httpx
from dotenv import load_dotenv

from pollers.gh_metadata import parse_greenhouse_metadata

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
        logger.info("Greenhouse: %d companies to re-poll for metadata backfill", len(slugs))

        updates: dict[str, dict] = {}
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
                    if not job_id:
                        continue
                    parsed = parse_greenhouse_metadata(job.get("metadata"))
                    if any(v is not None for v in parsed.values()):
                        updates[job_id] = parsed
            await asyncio.gather(*[fetch(s) for s in slugs])

        logger.info("Greenhouse: %d job_ids with at least one parsed field", len(updates))

        items = list(updates.items())
        applied = 0
        async with pool.acquire() as conn:
            for chunk in _chunks(items):
                await conn.execute(
                    """
                    UPDATE jobs AS j
                    SET raw_ats_metadata = COALESCE(j.raw_ats_metadata, '{}'::jsonb) || c.parsed
                    FROM (
                        SELECT unnest($1::text[]) AS job_id,
                               unnest($2::jsonb[]) AS parsed
                    ) AS c
                    WHERE j.job_id = c.job_id AND j.ats = 'greenhouse'
                    """,
                    [jid for jid, _ in chunk],
                    [json.dumps(parsed) for _, parsed in chunk],
                )
                applied += len(chunk)
                logger.info("Greenhouse metadata backfill: applied %d/%d", applied, len(items))

        logger.info("Greenhouse metadata backfill complete, %d rows updated", applied)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
