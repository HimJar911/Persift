"""One-time backfill: add 'country' into raw_ats_metadata on existing
SmartRecruiters/Ashby/Lever job rows.

Why a standalone script and not db.repair_metadata_batch: that function only
overwrites raw_ats_metadata when the existing value is NULL or '{}' (its
whole point is not to clobber rows that already have real captured data) —
but every row this backfill targets already has department/function/etc.
captured, so that guard would skip them all. This script instead merges the
new 'country' key into whatever raw_ats_metadata already exists via
Postgres's jsonb `||` operator, so it adds the field without touching
anything already there.

Re-polls each ATS live (same endpoints the regular pollers use) rather than
reading from a stale local file, so country reflects current job state.
Chunked per _BATCH_CHUNK_SIZE / decisions/0006 (unbounded batch writes hung
the ingestion pipeline for 13+ min at full volume once already).

Run: python scripts/backfill_country.py
"""

import asyncio
import json
import logging
import os

import asyncpg
import httpx
from dotenv import load_dotenv

from pollers.geography import (
    normalize_ashby_country,
    normalize_lever_country,
    normalize_smartrecruiters_country,
)

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_CHUNK_SIZE = 2000
_CONCURRENCY = 15


def _chunks(items: list, size: int = _CHUNK_SIZE):
    for i in range(0, len(items), size):
        yield items[i:i + size]


async def _apply_updates(pool: asyncpg.Pool, ats: str, updates: dict[str, str | None]) -> int:
    """updates: job_id -> country. Merges {'country': ...} into existing raw_ats_metadata."""
    items = list(updates.items())
    applied = 0
    async with pool.acquire() as conn:
        for chunk in _chunks(items):
            result = await conn.execute(
                """
                UPDATE jobs AS j
                SET raw_ats_metadata = COALESCE(j.raw_ats_metadata, '{}'::jsonb)
                    || jsonb_build_object('country', c.country)
                FROM (
                    SELECT unnest($1::text[]) AS job_id,
                           unnest($2::text[]) AS country
                ) AS c
                WHERE j.job_id = c.job_id AND j.ats = $3
                """,
                [jid for jid, _ in chunk],
                [country for _, country in chunk],
                ats,
            )
            applied += len(chunk)
            logger.info("%s: applied %d/%d", ats, applied, len(items))
    return applied


async def backfill_smartrecruiters(pool: asyncpg.Pool) -> None:
    slugs = [r["company_slug"] for r in await pool.fetch(
        "SELECT DISTINCT company_slug FROM jobs WHERE ats='smartrecruiters'"
    )]
    logger.info("SmartRecruiters: %d companies to re-poll", len(slugs))

    updates: dict[str, str | None] = {}
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
                        loc = job.get("location") or {}
                        updates[job_id] = normalize_smartrecruiters_country(loc.get("country"))
                    offset += 100
                    if offset >= data.get("totalFound", 0):
                        return
        await asyncio.gather(*[fetch(s) for s in slugs])

    logger.info("SmartRecruiters: %d job_ids with country data fetched", len(updates))
    applied = await _apply_updates(pool, "smartrecruiters", updates)
    logger.info("SmartRecruiters: backfill complete, %d rows updated", applied)


async def backfill_lever(pool: asyncpg.Pool) -> None:
    slugs = [r["company_slug"] for r in await pool.fetch(
        "SELECT DISTINCT company_slug FROM jobs WHERE ats='lever'"
    )]
    logger.info("Lever: %d companies to re-poll", len(slugs))

    updates: dict[str, str | None] = {}
    sem = asyncio.Semaphore(_CONCURRENCY)
    async with httpx.AsyncClient(timeout=25) as client:
        async def fetch(slug: str) -> None:
            async with sem:
                try:
                    r = await client.get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
                    if r.status_code != 200:
                        return
                    data = r.json()
                except Exception:
                    return
                if not isinstance(data, list):
                    return
                for job in data:
                    job_id = str(job.get("id", ""))
                    if not job_id:
                        continue
                    updates[job_id] = normalize_lever_country(job.get("country"))
        await asyncio.gather(*[fetch(s) for s in slugs])

    logger.info("Lever: %d job_ids with country data fetched", len(updates))
    applied = await _apply_updates(pool, "lever", updates)
    logger.info("Lever: backfill complete, %d rows updated", applied)


async def backfill_ashby(pool: asyncpg.Pool) -> None:
    slugs = [r["company_slug"] for r in await pool.fetch(
        "SELECT DISTINCT company_slug FROM jobs WHERE ats='ashby'"
    )]
    logger.info("Ashby: %d companies to re-poll", len(slugs))

    updates: dict[str, str | None] = {}
    sem = asyncio.Semaphore(_CONCURRENCY)
    async with httpx.AsyncClient(timeout=25) as client:
        async def fetch(slug: str) -> None:
            async with sem:
                try:
                    r = await client.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
                    if r.status_code != 200:
                        return
                    data = r.json()
                except Exception:
                    return
                for job in data.get("jobs", []):
                    job_id = str(job.get("id", ""))
                    if not job_id:
                        continue
                    addr = (job.get("address") or {}).get("postalAddress") or {}
                    updates[job_id] = normalize_ashby_country(addr.get("addressCountry"))
        await asyncio.gather(*[fetch(s) for s in slugs])

    logger.info("Ashby: %d job_ids with country data fetched", len(updates))
    applied = await _apply_updates(pool, "ashby", updates)
    logger.info("Ashby: backfill complete, %d rows updated", applied)


async def main() -> None:
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=2, max_size=10)
    try:
        await backfill_smartrecruiters(pool)
        await backfill_lever(pool)
        await backfill_ashby(pool)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
