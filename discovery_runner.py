"""Slim Render scheduler: Jobright poller only.

No Tier-1 ATSes, no matcher, no tailor worker, no API.
Worker A (run_discovery_cycle) disabled until BuiltWith integration is ready.
Runs one loop:
  - run_jobright_cycle() every 60 minutes
"""

import asyncio
import json
import logging
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx

from config import LOG_LEVEL
from db import init_db, close_db, get_pool
from pipeline.detector import detect_new_jobs
from pollers.filter import is_intern_role
from pollers.jobright import poll_jobright, resolve_apply_url, _RESOLVE_SEMAPHORE

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("persift.discovery")


# ---------------------------------------------------------------------------
# Health server (keeps Render web service alive)
# ---------------------------------------------------------------------------

class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health"):
            body = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_HEAD(self):
        if self.path in ("/", "/health"):
            body = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):  # silence access logs
        pass


def _start_health_server() -> None:
    port = int(os.environ.get("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"Health server started on port {port}", flush=True)


# ---------------------------------------------------------------------------
# Jobright state helpers (identical to main.py)
# ---------------------------------------------------------------------------

async def _load_jobright_timestamp() -> int:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT cursor FROM poller_state WHERE poller = 'jobright'"
        )
    if row is None:
        return 0
    return int(json.loads(row["cursor"]).get("since_ms", 0))


async def _save_jobright_timestamp(jobs: list[dict]) -> None:
    if not jobs:
        return
    max_ts = max(j.get("posted_at", 0) for j in jobs)
    if max_ts <= 0:
        return
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO poller_state (poller, last_run_at, cursor)
            VALUES ('jobright', NOW(), $1::jsonb)
            ON CONFLICT (poller) DO UPDATE
                SET last_run_at = NOW(),
                    cursor      = $1::jsonb
            """,
            json.dumps({"since_ms": max_ts}),
        )
    logger.info("Jobright timestamp saved — next run fetches jobs after %d", max_ts)


# ---------------------------------------------------------------------------
# discovery_staging insert
# ---------------------------------------------------------------------------

async def _stage_for_discovery(jobs: list[dict]) -> None:
    """Insert resolved Jobright jobs into discovery_staging for Worker A."""
    if not jobs:
        return
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO discovery_staging (job_id, job_ats, company_name, apply_url, raw_job)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            ON CONFLICT (job_id, job_ats) DO NOTHING
            """,
            [
                (
                    j["job_id"],
                    j["ats"],
                    j.get("company_name"),
                    j.get("apply_url") or None,
                    json.dumps(j),
                )
                for j in jobs
            ],
        )
    logger.info("Staged %d jobs into discovery_staging", len(jobs))


# ---------------------------------------------------------------------------
# Cycles
# ---------------------------------------------------------------------------

async def run_jobright_cycle() -> None:
    logger.info("=== Starting Jobright cycle ===")

    since_ts = await _load_jobright_timestamp()
    logger.info("Jobright: fetching with since_ms=%d", since_ts)

    raw_jobs = await poll_jobright(since_timestamp=since_ts)
    logger.info("Jobright: %d raw jobs from API", len(raw_jobs))

    if raw_jobs:
        timestamps = [j.get("posted_at", 0) for j in raw_jobs if j.get("posted_at")]
        if timestamps:
            logger.info(
                "Jobright: postedAt range %d – %d",
                min(timestamps), max(timestamps),
            )

    jobs = [j for j in raw_jobs if is_intern_role(j["title"])]
    logger.info("Jobright: %d jobs after is_intern_role filter", len(jobs))

    await _save_jobright_timestamp(jobs)

    new_jobs = await detect_new_jobs(jobs, "jobright")
    logger.info("Jobright: %d genuinely new (not yet in jobs table)", len(new_jobs))
    if not new_jobs:
        logger.info("=== Jobright cycle complete — no new jobs ===")
        return

    await _stage_for_discovery(new_jobs)
    logger.info("=== Jobright cycle complete — %d new jobs staged ===", len(new_jobs))


# ---------------------------------------------------------------------------
# Recurring loops (replace APScheduler — no event-loop integration issues)
# ---------------------------------------------------------------------------

async def _jobright_loop() -> None:
    """Polls Jobright every 60 minutes. Fires immediately on first iteration."""
    while True:
        logger.info("Jobright loop: iteration starting")
        try:
            await run_jobright_cycle()
        except Exception:
            logger.exception("Jobright cycle failed — will retry in 60 min")
        await asyncio.sleep(60 * 60)


# Worker A (run_discovery_cycle) is disabled until BuiltWith integration is
# available. Almost all staged companies end up queued_manual without it,
# and running it concurrently with the Jobright poller causes OOM on 512MB.


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    logger.info("Initializing Persift discovery runner")
    await init_db()

    try:
        logger.info("Loops started — Jobright every 60 min")
        await _jobright_loop()
    finally:
        await close_db()


if __name__ == "__main__":
    _start_health_server()
    asyncio.run(main())
