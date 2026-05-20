"""Postgres database layer using asyncpg.

Public API:
    init_db()             — create pool, call once at startup
    get_pool()            — return pool, raise if not initialized
    close_db()            — close pool cleanly at shutdown
    filter_new_ids(jobs)  — return subset of jobs not yet in the DB
    mark_seen_batch(jobs) — insert new jobs, ON CONFLICT DO NOTHING
"""

import logging
from datetime import datetime, timezone

import asyncpg

from config import DATABASE_URL

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def init_db() -> None:
    global _pool
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    logger.info("Postgres pool ready (min=2, max=10)")


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized — call init_db() first")
    return _pool


async def close_db() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Postgres pool closed")


async def filter_new_ids(jobs: list[dict]) -> list[dict]:
    """Return the subset of jobs not already in the jobs table.

    Checks by (job_id, ats) composite key using parallel unnest arrays
    so the whole batch is checked in a single round-trip.
    """
    if not jobs:
        return []
    pool = get_pool()
    job_ids = [j["job_id"] for j in jobs]
    ats_list = [j["ats"] for j in jobs]
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT j.job_id, j.ats
            FROM jobs j
            JOIN (
                SELECT unnest($1::text[]) AS job_id,
                       unnest($2::text[]) AS ats
            ) AS c ON j.job_id = c.job_id AND j.ats = c.ats
            """,
            job_ids,
            ats_list,
        )
    existing = {(r["job_id"], r["ats"]) for r in rows}
    return [j for j in jobs if (j["job_id"], j["ats"]) not in existing]


async def mark_seen_batch(jobs: list[dict]) -> None:
    """Insert jobs into the jobs table. Silently skips duplicates."""
    if not jobs:
        return
    pool = get_pool()
    now = datetime.now(timezone.utc)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO jobs (
                job_id, ats, company_slug, company_name, title,
                location, apply_url, description, categories,
                experience_level, work_model, h1b_sponsored,
                posted_at, first_seen_at
            )
            SELECT
                unnest($1::text[]),
                unnest($2::text[]),
                unnest($3::text[]),
                unnest($4::text[]),
                unnest($5::text[]),
                unnest($6::text[]),
                unnest($7::text[]),
                unnest($8::text[]),
                unnest($9::text[][]),
                unnest($10::text[]),
                unnest($11::text[]),
                unnest($12::text[]),
                unnest($13::bigint[]),
                unnest($14::timestamptz[])
            ON CONFLICT (job_id, ats) DO NOTHING
            """,
            [j["job_id"] for j in jobs],
            [j["ats"] for j in jobs],
            [j["company_slug"] for j in jobs],
            [j.get("company_name", "") for j in jobs],
            [j["title"] for j in jobs],
            [j.get("location", "Unknown") for j in jobs],
            [j.get("apply_url", "") for j in jobs],
            [j.get("description_plain_text", "") for j in jobs],
            [j.get("categories", []) for j in jobs],
            [j.get("experience_level", "") for j in jobs],
            [j.get("work_model", "Unknown") for j in jobs],
            [j.get("h1b_sponsored", "Not Sure") for j in jobs],
            [j.get("posted_at", 0) for j in jobs],
            [now] * len(jobs),
        )
    logger.info("Marked %d jobs as seen", len(jobs))
