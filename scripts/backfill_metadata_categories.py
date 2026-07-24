"""One-time backfill: apply pollers/metadata_categories.py's mapping to
existing job rows across all 4 ATSes, merging into whatever categories the
regex classifier already produced (never replacing — a job keeps every
category regex found, plus the metadata-derived one if it adds something
new).

Reads department/function metadata straight from raw_ats_metadata, which is
already backfilled on existing rows (country/function backfill for
SmartRecruiters, departments[] backfill for Greenhouse, both Jul 23 2026) —
no live re-poll needed for this step, just local computation + one UPDATE
pass per ATS.

Chunked per decisions/0006.

Run: python -m scripts.backfill_metadata_categories
"""

import asyncio
import logging
import os

import asyncpg
from dotenv import load_dotenv

from pollers.metadata_categories import (
    map_department,
    map_greenhouse_departments,
    map_smartrecruiters_function,
)

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_CHUNK_SIZE = 2000


def _chunks(items: list, size: int = _CHUNK_SIZE):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _to_pg_array(items: list[str]) -> str:
    if not items:
        return "{}"
    escaped = ['"' + item.replace("\\", "\\\\").replace('"', '\\"') + '"' for item in items]
    return "{" + ",".join(escaped) + "}"


async def _apply(pool: asyncpg.Pool, ats: str, updates: list[tuple[str, list[str]]]) -> int:
    applied = 0
    async with pool.acquire() as conn:
        for chunk in _chunks(updates):
            await conn.execute(
                """
                UPDATE jobs AS j
                SET categories = c.categories::text[]
                FROM (
                    SELECT unnest($1::text[]) AS job_id,
                           unnest($2::text[]) AS categories
                ) AS c
                WHERE j.job_id = c.job_id AND j.ats = $3
                """,
                [jid for jid, _ in chunk],
                [_to_pg_array(cats) for _, cats in chunk],
                ats,
            )
            applied += len(chunk)
            logger.info("%s: applied %d/%d", ats, applied, len(updates))
    return applied


async def backfill_smartrecruiters(pool: asyncpg.Pool) -> None:
    rows = await pool.fetch(
        "SELECT job_id, categories, raw_ats_metadata->'function'->>'label' AS fn "
        "FROM jobs WHERE ats='smartrecruiters'"
    )
    updates = []
    for r in rows:
        mapped = map_smartrecruiters_function(r["fn"])
        if mapped and mapped not in (r["categories"] or []):
            updates.append((r["job_id"], list(r["categories"] or []) + [mapped]))
    logger.info("SmartRecruiters: %d rows to update with a new category", len(updates))
    applied = await _apply(pool, "smartrecruiters", updates)
    logger.info("SmartRecruiters: category backfill complete, %d rows updated", applied)


async def backfill_department_ats(pool: asyncpg.Pool, ats: str) -> None:
    rows = await pool.fetch(
        f"SELECT job_id, categories, raw_ats_metadata->>'department' AS dept "
        f"FROM jobs WHERE ats='{ats}'"
    )
    updates = []
    for r in rows:
        mapped = map_department(r["dept"])
        if mapped and mapped not in (r["categories"] or []):
            updates.append((r["job_id"], list(r["categories"] or []) + [mapped]))
    logger.info("%s: %d rows to update with a new category", ats, len(updates))
    applied = await _apply(pool, ats, updates)
    logger.info("%s: category backfill complete, %d rows updated", ats, applied)


async def backfill_greenhouse(pool: asyncpg.Pool) -> None:
    rows = await pool.fetch(
        "SELECT job_id, categories, raw_ats_metadata->'departments' AS depts "
        "FROM jobs WHERE ats='greenhouse'"
    )
    updates = []
    for r in rows:
        import json
        depts = r["depts"]
        if isinstance(depts, str):
            depts = json.loads(depts)
        mapped = map_greenhouse_departments(depts)
        if mapped and mapped not in (r["categories"] or []):
            updates.append((r["job_id"], list(r["categories"] or []) + [mapped]))
    logger.info("Greenhouse: %d rows to update with a new category", len(updates))
    applied = await _apply(pool, "greenhouse", updates)
    logger.info("Greenhouse: category backfill complete, %d rows updated", applied)


async def main() -> None:
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=2, max_size=10)
    try:
        await backfill_smartrecruiters(pool)
        await backfill_department_ats(pool, "ashby")
        await backfill_department_ats(pool, "lever")
        await backfill_greenhouse(pool)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
