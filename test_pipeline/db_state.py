"""harness_runs / harness_job_state read/write layer.

Public API:
    start_run(ats, target_count, harness_version, notes=None) -> run_id
    seed_job_state(run_id, job_id, ats, sample_phase, harness_version) -> None
    seed_job_state_batch(run_id, rows, harness_version) -> None
    claim_next_pending(run_id, worker_id) -> dict | None
    update_job_outcome(run_id, job_id, ats, **fields) -> None
    get_run(run_id) -> dict
    get_pending_count(run_id) -> int
    get_recent_outcomes(run_id, sample_phase, limit) -> list[str]
    get_jobs_since_checkpoint(run_id, since_job_state_ctid=None, ...) -> list[dict]

Deliberately separate from db.py: harness state is test infrastructure, not
production polling/matching data, and migrations/025_harness_run_state.sql's
own comment explains why it isn't layered onto user_jobs.status. This module
follows the same asyncpg-pool-via-db.get_pool() convention as the rest of the
project rather than opening its own connection, so it shares the same pool
lifecycle (init_db()/close_db() in main.py-equivalents already call this).
"""

import hashlib
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from db import get_pool

logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent.parent

_TERMINAL_OUTCOMES = {
    "mechanically_verified", "needs_review_non_submit",
    "failed", "timeout", "harness_error", "skipped_blocked",
}


def compute_interpreter_version() -> str:
    """sha256 of corpus_analysis/interpreter_p14.py — interpreter_p14.py has
    no explicit version constant today, so a content hash is the cheapest
    reliable way to know if two runs used the same interpreter logic."""
    path = PROJECT_DIR / "corpus_analysis" / "interpreter_p14.py"
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def get_extension_commit_sha() -> str:
    """Git commit of extension/ as currently checked out. Best-effort — a
    dirty working tree still reports the last commit that touched it, which
    is a real limitation (uncommitted local edits wouldn't be reflected) but
    matches how every other commit-sha reference in this project works."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", "extension/"],
            cwd=PROJECT_DIR, capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except Exception:
        logger.warning("Could not determine extension/ commit sha", exc_info=True)
        return "unknown"


def get_regression_corpus_size() -> int:
    import json
    path = PROJECT_DIR / "corpus_analysis" / "interpreter_regressions.json"
    try:
        return len(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        logger.warning("Could not read interpreter_regressions.json", exc_info=True)
        return -1


async def start_run(ats: str, target_count: int, harness_version: str, notes: str | None = None) -> int:
    """Insert a new harness_runs row, stamped with the version metadata a
    later checkpoint needs to know whether two runs are directly comparable.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        run_id = await conn.fetchval(
            """
            INSERT INTO harness_runs
                (ats, target_count, harness_version, interpreter_version,
                 extension_commit_sha, regression_corpus_size, notes)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id
            """,
            ats, target_count, harness_version,
            compute_interpreter_version(), get_extension_commit_sha(),
            get_regression_corpus_size(), notes,
        )
    logger.info("Started harness run %d (ats=%s, target=%d)", run_id, ats, target_count)
    return run_id


async def get_run(run_id: int) -> dict:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM harness_runs WHERE id = $1", run_id)
    if row is None:
        raise ValueError(f"No harness_runs row for run_id={run_id}")
    return dict(row)


async def seed_job_state_batch(run_id: int, jobs: list[dict], harness_version: str) -> None:
    """Bulk-insert pending rows for a batch of {job_id, ats, sample_phase}
    dicts. ON CONFLICT DO NOTHING — re-seeding an already-seeded run (e.g.
    --resume-run-id) is a safe no-op per job, not an error."""
    if not jobs:
        return
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO harness_job_state (run_id, job_id, ats, sample_phase, outcome, harness_version)
            VALUES ($1, $2, $3, $4, 'pending', $5)
            ON CONFLICT (run_id, job_id, ats) DO NOTHING
            """,
            [(run_id, j["job_id"], j["ats"], j["sample_phase"], harness_version) for j in jobs],
        )
    logger.info("Seeded %d job_state rows for run %d", len(jobs), run_id)


async def claim_next_pending(run_id: int, worker_id: int) -> dict | None:
    """Atomically claim one pending job for this worker: FOR UPDATE SKIP
    LOCKED so concurrent workers never claim the same row (same real-world
    concurrency hazard /jobs/claim's own atomic UPDATE...RETURNING solves in
    api/server.py, applied here since harness_runner.py has N worker
    coroutines pulling from the same table).

    Sets outcome='claimed', not just worker_id/started_at — real bug found
    sanity-testing this module locally: leaving outcome='pending' on a
    claimed-but-not-yet-finished row made get_pending_count() overcount (an
    in-flight job still looked untouched) and would have let a second
    worker's claim query select the same row. See migrations/026."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT job_id, ats, sample_phase
                FROM harness_job_state
                WHERE run_id = $1 AND outcome = 'pending'
                ORDER BY job_id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
                run_id,
            )
            if row is None:
                return None
            await conn.execute(
                """
                UPDATE harness_job_state
                SET outcome = 'claimed', worker_id = $1, started_at = NOW()
                WHERE run_id = $2 AND job_id = $3 AND ats = $4
                """,
                worker_id, run_id, row["job_id"], row["ats"],
            )
    return dict(row)


async def update_job_outcome(
    run_id: int,
    job_id: str,
    ats: str,
    outcome: str,
    phase_reached: str | None = None,
    failure_reason: str | None = None,
    fields_filled: int | None = None,
    fields_total: int | None = None,
    page_fingerprint: str | None = None,
    debug_log_ref: str | None = None,
    harness_version: str | None = None,
) -> None:
    if outcome not in _TERMINAL_OUTCOMES:
        raise ValueError(f"Invalid terminal outcome {outcome!r}, must be one of {_TERMINAL_OUTCOMES}")
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE harness_job_state
            SET outcome = $1, phase_reached = $2, failure_reason = $3,
                fields_filled = $4, fields_total = $5, page_fingerprint = $6,
                debug_log_ref = $7, harness_version = COALESCE($8, harness_version),
                ended_at = NOW()
            WHERE run_id = $9 AND job_id = $10 AND ats = $11
            """,
            outcome, phase_reached, failure_reason, fields_filled, fields_total,
            page_fingerprint, debug_log_ref, harness_version, run_id, job_id, ats,
        )


async def get_pending_count(run_id: int) -> int:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT count(*) FROM harness_job_state WHERE run_id = $1 AND outcome = 'pending'",
            run_id,
        )


async def get_outcome_counts(run_id: int, sample_phase: str | None = None) -> dict[str, int]:
    """outcome -> count, optionally scoped to one sample_phase. Used by
    report.py's per-phase outcome summary and completion.py's volume check."""
    pool = get_pool()
    async with pool.acquire() as conn:
        if sample_phase is None:
            rows = await conn.fetch(
                "SELECT outcome, count(*) AS n FROM harness_job_state WHERE run_id = $1 GROUP BY outcome",
                run_id,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT outcome, count(*) AS n FROM harness_job_state
                WHERE run_id = $1 AND sample_phase = $2 GROUP BY outcome
                """,
                run_id, sample_phase,
            )
    return {r["outcome"]: r["n"] for r in rows}


async def get_recent_outcomes_in_order(run_id: int, sample_phase: str, limit: int) -> list[str]:
    """Most recent `limit` outcomes for one phase, newest first, ordered by
    ended_at — feeds completion.py's '150 consecutive clean' streak check."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT outcome FROM harness_job_state
            WHERE run_id = $1 AND sample_phase = $2 AND ended_at IS NOT NULL
            ORDER BY ended_at DESC
            LIMIT $3
            """,
            run_id, sample_phase, limit,
        )
    return [r["outcome"] for r in rows]


async def get_recent_outcomes_with_timestamps(run_id: int, sample_phase: str, limit: int) -> list[dict]:
    """Same as get_recent_outcomes_in_order but also returns ended_at —
    completion.py's criterion #2 needs to filter the consecutive-clean
    window to only jobs that finished AFTER the last accepted fix's commit
    timestamp, which get_recent_outcomes_in_order alone can't support.
    Kept as a separate function rather than changing that one's return
    shape, since it's already relied on elsewhere with the simpler
    contract."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT outcome, ended_at FROM harness_job_state
            WHERE run_id = $1 AND sample_phase = $2 AND ended_at IS NOT NULL
            ORDER BY ended_at DESC
            LIMIT $3
            """,
            run_id, sample_phase, limit,
        )
    return [{"outcome": r["outcome"], "ended_at": r["ended_at"]} for r in rows]


async def get_jobs_completed_since(run_id: int, since: datetime) -> list[dict]:
    """All job_state rows with ended_at > since — the accumulation window a
    checkpoint pass clusters over. `since` is the previous checkpoint's
    trigger time (or run start for the first checkpoint)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM harness_job_state WHERE run_id = $1 AND ended_at > $2 ORDER BY ended_at",
            run_id, since,
        )
    return [dict(r) for r in rows]


async def get_all_job_history(run_id: int) -> list[dict]:
    """Full run history, not just the current batch — cluster.py's
    paired-success lookup needs the run's entire mechanically_verified
    population, not just what accumulated since the last checkpoint."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM harness_job_state WHERE run_id = $1 AND ended_at IS NOT NULL ORDER BY ended_at",
            run_id,
        )
    return [dict(r) for r in rows]


async def count_completed_since_run_start(run_id: int) -> int:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT count(*) FROM harness_job_state WHERE run_id = $1 AND ended_at IS NOT NULL",
            run_id,
        )


async def get_distinct_page_fingerprints(run_id: int) -> set[str]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT page_fingerprint FROM harness_job_state WHERE run_id = $1 AND page_fingerprint IS NOT NULL",
            run_id,
        )
    return {r["page_fingerprint"] for r in rows}
