"""Postgres database layer using asyncpg.

Public API:
    init_db()                              — create pool, call once at startup
    get_pool()                             — return pool, raise if not initialized
    close_db()                             — close pool cleanly at shutdown
    filter_new_ids(jobs)                   — return subset of jobs not yet in the DB
    mark_seen_batch(jobs)                  — insert new jobs, ON CONFLICT DO NOTHING
    find_incomplete_ids(jobs)              — subset of given jobs whose DB row has empty fields
    repair_jobs_batch(jobs)                — fill empty description/company_name/apply_url in place
    repair_metadata_batch(jobs)            — backfill raw_ats_metadata on existing rows (one-time catch-up)
    get_company_payload_hash(s, a)         — read (last_payload_hash, last_response_etag) for a company
    set_company_payload_hash(s, a, h, e)   — store this poll's payload hash/etag for next cycle
    increment_consecutive_failures(s, a)   — bump failure counter; deactivate at 5
    reset_consecutive_failures(s, a)       — reset counter to 0 on successful poll
    log_company_poll(...)                  — append one row to company_poll_log
"""

import json
import logging
from datetime import datetime, timezone

import asyncpg

from config import DATABASE_URL

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None

# Max rows per batch INSERT/UPDATE statement. mark_seen_batch/repair_jobs_batch/
# repair_metadata_batch build their SQL params as Python lists (one list per
# column, unnest()'d in the query) — at full-poll-cycle volume (one ATS alone
# returned 228K jobs in a single Jul 22 cycle) an unbatched call holds the
# entire set in memory as parallel Python lists plus per-row JSON/string
# encoding, which starves the event loop long enough to look hung (confirmed
# live: 13+ minutes with the query's wait_event stuck on ClientRead — Postgres
# idle, waiting on the client — not a slow query, a client-side bottleneck).
_BATCH_CHUNK_SIZE = 2000


def _chunks(items: list, size: int = _BATCH_CHUNK_SIZE):
    for i in range(0, len(items), size):
        yield items[i:i + size]


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
    existing: set[tuple[str, str]] = set()
    async with pool.acquire() as conn:
        for chunk in _chunks(jobs):
            rows = await conn.fetch(
                """
                SELECT j.job_id, j.ats
                FROM jobs j
                JOIN (
                    SELECT unnest($1::text[]) AS job_id,
                           unnest($2::text[]) AS ats
                ) AS c ON j.job_id = c.job_id AND j.ats = c.ats
                """,
                [j["job_id"] for j in chunk],
                [j["ats"] for j in chunk],
            )
            existing.update((r["job_id"], r["ats"]) for r in rows)
    return [j for j in jobs if (j["job_id"], j["ats"]) not in existing]


async def find_incomplete_ids(jobs: list[dict]) -> set[tuple[str, str]]:
    """Return {(job_id, ats)} of the given jobs whose DB row has an empty
    description, company_name, or apply_url.

    Used by the self-healing repair pass in detect_new_jobs: rows inserted
    before the Jul-2026 enrich-before-insert fix sit with empty fields, and
    this identifies the ones the current poll can repair. Returns nothing at
    steady state, so the repair pass costs ~one indexed SELECT per cycle.
    """
    if not jobs:
        return set()
    pool = get_pool()
    incomplete: set[tuple[str, str]] = set()
    async with pool.acquire() as conn:
        for chunk in _chunks(jobs):
            rows = await conn.fetch(
                """
                SELECT j.job_id, j.ats
                FROM jobs j
                JOIN (
                    SELECT unnest($1::text[]) AS job_id,
                           unnest($2::text[]) AS ats
                ) AS c ON j.job_id = c.job_id AND j.ats = c.ats
                WHERE j.description = '' OR j.company_name = '' OR j.apply_url = ''
                """,
                [j["job_id"] for j in chunk],
                [j["ats"] for j in chunk],
            )
            incomplete.update((r["job_id"], r["ats"]) for r in rows)
    return incomplete


async def repair_jobs_batch(jobs: list[dict]) -> None:
    """Fill empty description/company_name/apply_url on existing rows from
    freshly polled + enriched data. Never overwrites a non-empty value, and
    never writes an empty value over an empty value (no-op in that case).

    Expects enriched dicts (description under 'description_plain_text').
    """
    if not jobs:
        return
    pool = get_pool()
    async with pool.acquire() as conn:
        for chunk in _chunks(jobs):
            await conn.execute(
                """
                UPDATE jobs AS j SET
                    description  = CASE WHEN j.description  = '' AND c.description  <> ''
                                        THEN c.description  ELSE j.description  END,
                    company_name = CASE WHEN j.company_name = '' AND c.company_name <> ''
                                        THEN c.company_name ELSE j.company_name END,
                    apply_url    = CASE WHEN j.apply_url    = '' AND c.apply_url    <> ''
                                        THEN c.apply_url    ELSE j.apply_url    END
                FROM (
                    SELECT unnest($1::text[]) AS job_id,
                           unnest($2::text[]) AS ats,
                           unnest($3::text[]) AS description,
                           unnest($4::text[]) AS company_name,
                           unnest($5::text[]) AS apply_url
                ) AS c
                WHERE j.job_id = c.job_id AND j.ats = c.ats
                """,
                [j["job_id"] for j in chunk],
                [j["ats"] for j in chunk],
                [j.get("description_plain_text", "") for j in chunk],
                [j.get("company_name", "") for j in chunk],
                [j.get("apply_url", "") for j in chunk],
            )
    logger.info("Repaired empty fields on %d job rows", len(jobs))


async def repair_metadata_batch(jobs: list[dict]) -> None:
    """Backfill raw_ats_metadata on existing rows from a fresh poll.

    One-time catch-up for the Jul 22 capture-gap fixes (Greenhouse
    'departments', Lever 'department') — mark_seen_batch's ON CONFLICT DO
    NOTHING means a normal re-poll never touches rows already in the table,
    so existing Greenhouse/Lever/SmartRecruiters jobs would otherwise never
    pick up the newly-captured fields. Only overwrites when the existing row
    has NULL or '{}' raw_ats_metadata — never clobbers a row that already has
    real captured data.
    """
    if not jobs:
        return
    pool = get_pool()
    async with pool.acquire() as conn:
        for chunk in _chunks(jobs):
            await conn.execute(
                """
                UPDATE jobs AS j SET raw_ats_metadata = c.raw_ats_metadata
                FROM (
                    SELECT unnest($1::text[]) AS job_id,
                           unnest($2::text[]) AS ats,
                           unnest($3::jsonb[]) AS raw_ats_metadata
                ) AS c
                WHERE j.job_id = c.job_id AND j.ats = c.ats
                  AND (j.raw_ats_metadata IS NULL OR j.raw_ats_metadata = '{}'::jsonb)
                """,
                [j["job_id"] for j in chunk],
                [j["ats"] for j in chunk],
                [json.dumps(j["raw_ats_metadata"]) if j.get("raw_ats_metadata") is not None else None
                 for j in chunk],
            )
    logger.info("Backfilled raw_ats_metadata on up to %d existing job rows", len(jobs))


def _to_pg_array(items: list[str]) -> str:
    """Encode a Python list of strings as a PostgreSQL array literal.

    Needed because unnest(text[][]) flattens all dimensions — PostgreSQL has
    no single-dimension unnest for 2D arrays. Instead we pass each categories
    list as a text literal (e.g. '{"swe","ml_ai"}') inside a text[], then cast
    each element back to text[] inside the query with ::text[].
    """
    if not items:
        return "{}"
    escaped = ['"' + item.replace("\\", "\\\\").replace('"', '\\"') + '"' for item in items]
    return "{" + ",".join(escaped) + "}"


async def mark_seen_batch(jobs: list[dict]) -> None:
    """Insert jobs into the jobs table. Silently skips duplicates.

    years_of_experience_min/max (migration 022, pollers/seniority.py):
    literal "N years of experience" extraction only — NULL means the
    posting never stated a number, not "unknown, guess something." No
    categorical seniority label; see migration 022's header comment for
    why that design was rejected. raw_ats_metadata carries whatever
    structured fields the source ATS returned, verbatim, for future reuse
    without re-polling.
    """
    if not jobs:
        return
    pool = get_pool()
    now = datetime.now(timezone.utc)
    async with pool.acquire() as conn:
        for chunk in _chunks(jobs):
            await conn.execute(
                """
                INSERT INTO jobs (
                    job_id, ats, company_slug, company_name, title,
                    location, apply_url, description, categories,
                    experience_level, work_model, h1b_sponsored,
                    posted_at, first_seen_at,
                    years_of_experience_min, years_of_experience_max,
                    raw_ats_metadata
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
                    unnest($9::text[])::text[],
                    unnest($10::text[]),
                    unnest($11::text[]),
                    unnest($12::text[]),
                    unnest($13::bigint[]),
                    unnest($14::timestamptz[]),
                    unnest($15::smallint[]),
                    unnest($16::smallint[]),
                    unnest($17::jsonb[])
                ON CONFLICT (job_id, ats) DO NOTHING
                """,
                [j["job_id"] for j in chunk],
                [j["ats"] for j in chunk],
                [j["company_slug"] for j in chunk],
                [j.get("company_name", "") for j in chunk],
                [j["title"] for j in chunk],
                [j.get("location", "Unknown") for j in chunk],
                [j.get("apply_url", "") for j in chunk],
                [j.get("description_plain_text", "") for j in chunk],
                [_to_pg_array(j.get("categories", [])) for j in chunk],
                [j.get("experience_level", "") for j in chunk],
                [j.get("work_model", "Unknown") for j in chunk],
                [j.get("h1b_sponsored", "Not Sure") for j in chunk],
                [j.get("posted_at", 0) for j in chunk],
                [now] * len(chunk),
                [j.get("years_of_experience_min") for j in chunk],
                [j.get("years_of_experience_max") for j in chunk],
                [json.dumps(j["raw_ats_metadata"]) if j.get("raw_ats_metadata") is not None else None
                 for j in chunk],
            )
    logger.info("Marked %d jobs as seen", len(jobs))


async def increment_consecutive_failures(slug: str, ats: str) -> None:
    """Increment failure counter for a company; flip is_active=false at 5 failures."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE companies
            SET consecutive_failures = consecutive_failures + 1,
                is_active = CASE WHEN consecutive_failures + 1 >= 5 THEN FALSE ELSE is_active END
            WHERE ats = $1 AND slug = $2
            """,
            ats, slug,
        )


async def reset_consecutive_failures(slug: str, ats: str) -> None:
    """Reset failure counter to 0 after a successful poll."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE companies SET consecutive_failures = 0 WHERE ats = $1 AND slug = $2",
            ats, slug,
        )


async def get_company_payload_hash(slug: str, ats: str) -> tuple[str | None, str | None]:
    """Return (last_payload_hash, last_response_etag) for a company.

    Used by pollers to skip a company's response entirely (no parse, no
    filter_new_ids, no repair passes) when nothing changed since last poll —
    see migration 024's header comment for why (a Jul 22 incident where an
    unbatched full-poll DB write hung for 13+ minutes over jobs that hadn't
    actually changed).
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT last_payload_hash, last_response_etag FROM companies WHERE ats = $1 AND slug = $2",
            ats, slug,
        )
    if row is None:
        return None, None
    return row["last_payload_hash"], row["last_response_etag"]


async def set_company_payload_hash(
    slug: str, ats: str, payload_hash: str | None, etag: str | None = None,
) -> None:
    """Store this poll's payload hash/etag for next cycle's change check."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE companies SET last_payload_hash = $1, last_response_etag = $2 "
            "WHERE ats = $3 AND slug = $4",
            payload_hash, etag, ats, slug,
        )


async def log_company_poll(
    slug: str,
    ats: str,
    outcome: str,
    *,
    http_status: int | None = None,
    job_count: int = 0,
    matched_count: int = 0,
    error_detail: str | None = None,
) -> None:
    """Append one row to company_poll_log for a single poll attempt.

    outcome must be one of company_poll_log's CHECK values (migration 021):
    ok_with_jobs, ok_zero_jobs, http_404, http_429, http_4xx, http_5xx,
    timeout, connection_error, other_exception.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO company_poll_log
                (slug, ats, outcome, http_status, job_count, matched_count, error_detail)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            slug, ats, outcome, http_status, job_count, matched_count, error_detail,
        )
