"""CLI entrypoint + worker pool orchestration for the self-healing Greenhouse
test pipeline. Per joyful-sprouting-swan.md's "Orchestration" section.

Usage:
    python -m test_pipeline.harness_runner --ats greenhouse --count 1000 --workers 2 --checkpoint-every 50
    python -m test_pipeline.harness_runner --resume-run-id 4
"""

import argparse
import asyncio
import hashlib
import json
import logging
import random
import sys
import time
from pathlib import Path

from playwright.async_api import async_playwright

import test_pipeline.db_state as db_state
from db import close_db, init_db
from test_pipeline.circuit_breaker import CircuitBreaker
from test_pipeline.failure_log import (
    FieldFailure, JobFailureRecord, append_failure, failures_path_for_run,
)
from test_pipeline.job_driver import WorkerContext, run_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("harness-runner")

HARNESS_VERSION = "0.1.0"

PROJECT_DIR = Path(__file__).resolve().parent.parent
EXT_PATH = PROJECT_DIR / "extension"
PROFILES_DIR = PROJECT_DIR / "test_pipeline_profiles"
CORPUS_ANALYSIS_DIR = PROJECT_DIR / "corpus_analysis"

_DEFAULT_API_BASE = "http://127.0.0.1:8000"

# Every ~150-200 jobs per worker, per the plan's "Orchestration" section —
# defensive against long-session Chromium memory creep, same lesson as
# corpus_harvester.py's browser recycling even though the mechanism differs
# (per-worker persistent contexts here, not one shared browser).
_CONTEXT_RECYCLE_EVERY = 175

# Long-tail clusters at/under this member count are Phase B's target pool —
# a number to sanity-check against the real distribution, per the plan
# ("e.g. clusters with under ~30 corpus-wide members"). Confirmed live
# 2026-08-06: 2,779 of 3,702 clusters in clusters_v2.json are under this
# threshold, a real long tail, not a degenerate edge case.
_PHASE_B_RARITY_THRESHOLD = 30


# ---------------------------------------------------------------------------
# Job selection — two phases, per the plan's "Job selection" section
# ---------------------------------------------------------------------------

async def _select_phase_a(count: int) -> list[dict]:
    """Random sample of untouched Greenhouse jobs — measures baseline
    robustness. Same untouched-pool query shape as the plan specifies."""
    pool = db_state.get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT j.job_id, j.ats
            FROM jobs j
            LEFT JOIN user_jobs uj ON uj.job_id = j.job_id AND uj.job_ats = j.ats
            WHERE j.ats = 'greenhouse' AND uj.id IS NULL
            ORDER BY random()
            LIMIT $1
            """,
            count,
        )
    return [{"job_id": r["job_id"], "ats": r["ats"], "sample_phase": "A"} for r in rows]


def _load_phase_b_candidate_job_ids(rarity_threshold: int = _PHASE_B_RARITY_THRESHOLD) -> list[str]:
    """Long-tail job_ids from clusters_v2.json: the smallest clusters
    (by member count) below rarity_threshold, deduped across clusters.
    residue entries are a secondary pool per the plan, not used here unless
    the primary target list runs short (see _select_phase_b)."""
    clusters_path = CORPUS_ANALYSIS_DIR / "clusters_v2.json"
    data = json.loads(clusters_path.read_text(encoding="utf-8"))
    clusters = data.get("clusters", [])

    rare = [c for c in clusters if len(c.get("members", [])) <= rarity_threshold]
    rare.sort(key=lambda c: len(c.get("members", [])))

    job_ids: list[str] = []
    seen = set()
    for c in rare:
        for m in c.get("members", []):
            jid = m.get("job_id")
            if jid and jid not in seen:
                seen.add(jid)
                job_ids.append(jid)
    return job_ids


def _load_phase_b_residue_job_ids() -> list[str]:
    """Secondary pool: residue entries (fields the corpus's open-coding pass
    never resolved into a named cluster) — used only if the primary
    long-tail pool runs short, per the plan."""
    clusters_path = CORPUS_ANALYSIS_DIR / "clusters_v2.json"
    data = json.loads(clusters_path.read_text(encoding="utf-8"))
    residue = data.get("residue", [])
    job_ids: list[str] = []
    seen = set()
    for entry in residue:
        jid = entry.get("job_id")
        if jid and jid not in seen:
            seen.add(jid)
            job_ids.append(jid)
    return job_ids


async def _select_phase_b(count: int) -> list[dict]:
    """Targeted long-tail sample: rare structurally-clustered fields,
    deliberately over-sampling forms the interpreter has seen least of.
    Falls back to residue entries if the primary pool is smaller than
    `count` (a real possibility for genuinely rare structures)."""
    candidate_ids = _load_phase_b_candidate_job_ids()
    if len(candidate_ids) < count:
        logger.info(
            "Phase B primary pool (%d job_ids) smaller than target %d — "
            "extending with residue entries.", len(candidate_ids), count,
        )
        residue_ids = _load_phase_b_residue_job_ids()
        existing = set(candidate_ids)
        for jid in residue_ids:
            if jid not in existing:
                candidate_ids.append(jid)
                existing.add(jid)

    sample_ids = candidate_ids if len(candidate_ids) <= count else random.sample(candidate_ids, count)

    if not sample_ids:
        return []

    pool = db_state.get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT j.job_id, j.ats
            FROM jobs j
            LEFT JOIN user_jobs uj ON uj.job_id = j.job_id AND uj.job_ats = j.ats
            WHERE j.ats = 'greenhouse' AND j.job_id = ANY($1::text[]) AND uj.id IS NULL
            """,
            sample_ids,
        )
    return [{"job_id": r["job_id"], "ats": r["ats"], "sample_phase": "B"} for r in rows]


# ---------------------------------------------------------------------------
# Page fingerprint novelty tracking (checkpoint-report signal, per the
# plan's "distinct page fingerprints seen: N (X new this batch)")
# ---------------------------------------------------------------------------

class _SharedState:
    def __init__(self, checkpoint_every: int) -> None:
        self.circuit_breaker = CircuitBreaker(checkpoint_every=checkpoint_every)
        self.completed = 0
        self.write_lock = asyncio.Lock()
        self.stop_requested = False
        self.jobs_since_last_checkpoint = 0
        self.checkpoint_every = checkpoint_every
        self.known_fingerprints: set[str] = set()
        self.new_fingerprints_this_batch = 0


async def _get_or_relaunch_context(p, profile_dir: Path, jobs_since_launch: int):
    """Launches (or the caller relaunches) one worker's persistent Chrome
    context loaded with the real, unmodified extension. Recycling is the
    caller's responsibility (see _worker) — this just launches fresh."""
    profile_dir.mkdir(parents=True, exist_ok=True)
    context = await p.chromium.launch_persistent_context(
        str(profile_dir),
        headless=False,
        args=[
            f"--disable-extensions-except={EXT_PATH}",
            f"--load-extension={EXT_PATH}",
        ],
    )
    sw = None
    for _ in range(20):
        if context.service_workers:
            sw = context.service_workers[0]
            break
        try:
            sw = await context.wait_for_event("serviceworker", timeout=1000)
            break
        except Exception:
            pass
    if sw is None:
        await context.close()
        raise RuntimeError(f"Extension service worker never registered for profile {profile_dir}")
    return context, sw


def _field_failures_from_result(result) -> list[FieldFailure]:
    return result.field_failures


async def _lookup_company_name(job_id: str, ats: str) -> str:
    pool = db_state.get_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval(
            "SELECT company_name FROM jobs WHERE job_id = $1 AND ats = $2", job_id, ats,
        )
    return val or ""


async def _worker(
    worker_id: int,
    p,
    state: _SharedState,
    run_id: int,
    user_id: str,
    api_base_url: str,
    failures_path: Path,
) -> None:
    """Each worker claims its own jobs directly from harness_job_state via
    db_state.claim_next_pending()'s FOR UPDATE SKIP LOCKED — not drained
    from a shared in-memory queue upfront, since that would both defeat the
    point of SKIP LOCKED (built for concurrent per-worker claiming) and
    mislabel every job's worker_id column with whichever worker happened to
    drain the queue first rather than the one that actually processed it."""
    profile_dir = PROFILES_DIR / f"worker_{worker_id}"
    jobs_since_launch = 0
    context = None
    sw = None

    try:
        context, sw = await _get_or_relaunch_context(p, profile_dir, jobs_since_launch)

        while True:
            if state.stop_requested:
                return

            job = await db_state.claim_next_pending(run_id, worker_id)
            if job is None:
                return
            job["company_name"] = await _lookup_company_name(job["job_id"], job["ats"])

            # Recycle before pulling this job if due — same reasoning as
            # corpus_harvester.py's browser recycling, adapted to per-worker
            # persistent contexts: proactively bound any long-session
            # Chromium memory creep rather than wait for a crash.
            if jobs_since_launch >= _CONTEXT_RECYCLE_EVERY:
                logger.info("[w%d] Recycling context after %d jobs.", worker_id, jobs_since_launch)
                try:
                    await context.close()
                except Exception:
                    pass
                context, sw = await _get_or_relaunch_context(p, profile_dir, 0)
                jobs_since_launch = 0

            ctx = WorkerContext(
                worker_id=worker_id, context=context, service_worker=sw,
                user_id=user_id, api_base_url=api_base_url, run_id=run_id,
                harness_version=HARNESS_VERSION,
            )

            # The entire per-job body is defensive: nothing here may
            # propagate out of this loop iteration, same discipline as
            # corpus_harvester.py's _worker — asyncio.gather cancels every
            # sibling worker the instant any one of them raises.
            try:
                result = await run_job(ctx, job)
                jobs_since_launch += 1
            except Exception:
                logger.error("[w%d] run_job raised for job %s — recording harness_error.", worker_id, job["job_id"], exc_info=True)
                await db_state.update_job_outcome(
                    run_id, job["job_id"], job["ats"], outcome="harness_error",
                    failure_reason="unhandled exception in run_job, see harness log",
                    harness_version=HARNESS_VERSION,
                )
                jobs_since_launch += 1
                async with state.write_lock:
                    state.completed += 1
                    state.jobs_since_last_checkpoint += 1
                    state.circuit_breaker.record_outcome("harness_error")
                continue

            async with state.write_lock:
                state.completed += 1
                state.jobs_since_last_checkpoint += 1
                state.circuit_breaker.record_outcome(result.outcome)

                if result.page_block_detected:
                    state.circuit_breaker.record_page_block(result.page_block_reason or "unspecified")

                if result.page_fingerprint and result.page_fingerprint not in state.known_fingerprints:
                    state.known_fingerprints.add(result.page_fingerprint)
                    state.new_fingerprints_this_batch += 1

                if result.outcome not in ("mechanically_verified",):
                    record = JobFailureRecord(
                        harness_version=HARNESS_VERSION, run_id=run_id,
                        job_id=result.job_id, ats=result.ats, sample_phase=job["sample_phase"],
                        company_name=job.get("company_name", ""), outcome=result.outcome,
                        phase_reached=result.phase_reached, worker_id=worker_id,
                        field_failures=_field_failures_from_result(result),
                        debug_log_ref=result.debug_log_ref,
                    )
                    append_failure(failures_path, record)

                logger.info(
                    "[w%d %d] %s (%s) -> %s%s",
                    worker_id, state.completed, job.get("company_name", ""), job["job_id"],
                    result.outcome,
                    f" ({result.fields_filled}/{result.fields_total} fields)" if result.fields_filled is not None else "",
                )

                if state.circuit_breaker.should_halt:
                    logger.warning(
                        "[w%d] Circuit breaker tripped: %s", worker_id, state.circuit_breaker.status_summary(),
                    )
                    state.stop_requested = True

    finally:
        if context is not None:
            try:
                await context.close()
            except Exception:
                pass


async def _drain_remaining_as_skipped_blocked(run_id: int) -> int:
    """When the circuit breaker halts on a real page-level block, mark every
    still-pending job for this run as skipped_blocked rather than leaving
    them silently 'pending' forever."""
    pool = db_state.get_pool()
    async with pool.acquire() as conn:
        tag = await conn.execute(
            """
            UPDATE harness_job_state
            SET outcome = 'skipped_blocked', ended_at = NOW()
            WHERE run_id = $1 AND outcome = 'pending'
            """,
            run_id,
        )
    try:
        return int(tag.split()[-1])
    except (IndexError, ValueError):
        return 0


async def run_harness(
    ats: str,
    count: int,
    workers: int,
    checkpoint_every: int,
    resume_run_id: int | None,
    api_base_url: str,
) -> None:
    await init_db()
    try:
        pool = db_state.get_pool()
        async with pool.acquire() as conn:
            test_users = await conn.fetch("SELECT id FROM users ORDER BY email")
        if len(test_users) < workers:
            raise RuntimeError(
                f"Need at least {workers} test users (one per worker), found {len(test_users)}. "
                f"Seed more via the same clone-and-INSERT approach used for the existing test users."
            )
        user_ids = [str(r["id"]) for r in test_users[:workers]]

        if resume_run_id is not None:
            run_id = resume_run_id
            run = await db_state.get_run(run_id)
            logger.info("Resuming run %d (ats=%s, target=%d)", run_id, run["ats"], run["target_count"])
        else:
            run_id = await db_state.start_run(ats, target_count=count, harness_version=HARNESS_VERSION)

            per_phase = count // 2
            phase_a_jobs = await _select_phase_a(per_phase)
            phase_b_jobs = await _select_phase_b(count - per_phase)
            logger.info("Selected %d Phase-A jobs, %d Phase-B jobs.", len(phase_a_jobs), len(phase_b_jobs))

            await db_state.seed_job_state_batch(run_id, phase_a_jobs + phase_b_jobs, HARNESS_VERSION)

        pending = await db_state.get_pending_count(run_id)
        logger.info("Run %d: %d pending job(s) to process with %d worker(s).", run_id, pending, workers)
        if pending == 0:
            logger.info("Nothing pending — run already complete or fully seeded-and-processed.")
            return

        failures_path = failures_path_for_run(run_id)
        state = _SharedState(checkpoint_every=checkpoint_every)
        start_time = time.monotonic()

        async with async_playwright() as p:
            worker_tasks = [
                asyncio.create_task(
                    _worker(w, p, state, run_id, user_ids[w - 1], api_base_url, failures_path)
                )
                for w in range(1, workers + 1)
            ]
            await asyncio.gather(*worker_tasks, return_exceptions=True)

        if state.circuit_breaker.page_block_tripped:
            n_marked = await _drain_remaining_as_skipped_blocked(run_id)
            logger.warning(
                "Circuit breaker halted on a page-level block (%s) — %d remaining job(s) marked skipped_blocked.",
                state.circuit_breaker.page_block_reason, n_marked,
            )

        elapsed = time.monotonic() - start_time
        outcomes = await db_state.get_outcome_counts(run_id)
        fingerprints = await db_state.get_distinct_page_fingerprints(run_id)

        _hr = "─" * 62
        print(_hr)
        print(f"  HARNESS RUN {run_id} — batch complete")
        for outcome, n in sorted(outcomes.items(), key=lambda kv: -kv[1]):
            print(f"  {outcome:28s} {n:4d}")
        print(f"  distinct page fingerprints seen: {len(fingerprints)} ({state.new_fingerprints_this_batch} new this batch)")
        print(f"  elapsed: {elapsed / 60:.1f} min")
        if state.circuit_breaker.should_force_early_checkpoint or state.jobs_since_last_checkpoint >= checkpoint_every:
            print(f"  -> checkpoint pass due (see test_pipeline/checkpoint/) — {state.jobs_since_last_checkpoint} jobs since last checkpoint")
        print(_hr, flush=True)
    finally:
        await close_db()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ats", default="greenhouse")
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--checkpoint-every", type=int, default=50)
    parser.add_argument("--resume-run-id", type=int, default=None)
    parser.add_argument("--api-base-url", default=_DEFAULT_API_BASE)
    args = parser.parse_args()

    asyncio.run(run_harness(
        ats=args.ats, count=args.count, workers=args.workers,
        checkpoint_every=args.checkpoint_every, resume_run_id=args.resume_run_id,
        api_base_url=args.api_base_url,
    ))


if __name__ == "__main__":
    main()
