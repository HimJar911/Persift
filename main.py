import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

import httpx

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import POLL_INTERVAL_MINUTES, LOG_LEVEL
from db import init_db, close_db, get_pool
from pollers.greenhouse import poll_greenhouse
from pollers.lever import poll_lever
from pollers.ashby import poll_ashby
from pollers.workday import poll_workday
from pollers.smartrecruiters import poll_smartrecruiters
from pollers.custom import poll_custom
from pollers.jobright import poll_jobright, resolve_apply_url, _RESOLVE_SEMAPHORE
from pollers.filter import is_entry_level, is_intern_role
from pipeline.detector import detect_new_jobs
from pipeline.enricher import enrich
from pipeline.tailor import tailor_resume, _build_plain_text_from_json, _load_base_resume
from pipeline.pdf_gen import convert_docx_to_pdf, generate_pdf_fallback
from pipeline.docx_editor import edit_docx
from pipeline.matcher import run_matching_cycle
from pipeline.tailor_worker import run_tailor_cycle
from pipeline.notifier import send_slack_notification


logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("persift")

PROJECT_DIR = Path(__file__).resolve().parent

async def _load_jobright_timestamp() -> int:
    """Return the last successful Jobright run timestamp from poller_state. Returns 0 on first run."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT cursor FROM poller_state WHERE poller = 'jobright'"
        )
    if row is None:
        return 0
    return int(json.loads(row["cursor"]).get("since_ms", 0))


async def _save_jobright_timestamp(jobs: list[dict]) -> None:
    """Persist the max postedAt timestamp to poller_state for the next run's filter."""
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
    logger.info("Jobright state saved — next run will fetch jobs after %d", max_ts)

COMPANY_FILES = {
    "greenhouse": PROJECT_DIR / "greenhouse_companies.json",
    "lever": PROJECT_DIR / "lever_companies.json",
    "ashby": PROJECT_DIR / "ashby_companies.json",
    "workday": PROJECT_DIR / "workday_companies.json",
    "smartrecruiters": PROJECT_DIR / "smartrecruiters_companies.json",
    "custom": PROJECT_DIR / "custom_companies.json",
}

COMPANY_FILE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60  # 30 days

# Limits concurrent OpenAI API calls so we don't blow through rate limits.
# Keep at 2 to stay within the 30K TPM limit on gpt-4o.
TAILOR_SEMAPHORE = asyncio.Semaphore(2)

# Company lists populated at startup.
_greenhouse_slugs: list[str] = []
_lever_slugs: list[str] = []
_ashby_slugs: list[str] = []
_workday_companies: list[dict] = []  # list of dicts with slug, wd_num, board, base_url
_smartrecruiters_slugs: list[str] = []
_custom_companies: list[dict] = []  # list of dicts from custom_companies.json


def _file_is_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    age = time.time() - path.stat().st_mtime
    return age < COMPANY_FILE_MAX_AGE_SECONDS


def _load_company_file(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list) and data:
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return []


def _all_company_files_fresh() -> bool:
    return all(_file_is_fresh(p) for p in COMPANY_FILES.values())


async def _run_discovery(crawl: str | None = None) -> None:
    """Run the Common Crawl discovery script as an async subprocess."""
    cmd = [sys.executable, str(PROJECT_DIR / "discover_companies.py")]
    if crawl:
        cmd.extend(["--crawl", crawl])

    logger.info("Running company discovery via Common Crawl...")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    if stdout:
        for line in stdout.decode().splitlines():
            logger.info("[discover] %s", line)

    if proc.returncode != 0:
        logger.error("Discovery script exited with code %d", proc.returncode)


def load_company_lists() -> None:
    """Load company lists from the JSON files into module-level lists."""
    global _greenhouse_slugs, _lever_slugs, _ashby_slugs
    global _workday_companies, _smartrecruiters_slugs, _custom_companies

    _greenhouse_slugs = _load_company_file(COMPANY_FILES["greenhouse"])
    _lever_slugs = _load_company_file(COMPANY_FILES["lever"])
    _ashby_slugs = _load_company_file(COMPANY_FILES["ashby"])

    # Workday uses a list of dicts, not plain slugs
    _workday_companies = _load_company_file(COMPANY_FILES["workday"])
    _smartrecruiters_slugs = _load_company_file(COMPANY_FILES["smartrecruiters"])
    _custom_companies = _load_company_file(COMPANY_FILES["custom"])

    counts = {
        "Greenhouse": len(_greenhouse_slugs),
        "Lever": len(_lever_slugs),
        "Ashby": len(_ashby_slugs),
        "Workday": len(_workday_companies),
        "SmartRecruiters": len(_smartrecruiters_slugs),
        "Custom": len(_custom_companies),
    }
    for name, count in counts.items():
        logger.info("%s: %d companies loaded", name, count)
    total = sum(counts.values())
    logger.info("Total: %d companies across %d ATS platforms", total, len(counts))


async def process_single_job(raw_job: dict) -> None:
    """Enrich and notify — tailoring and PDF disabled for testing."""
    job = enrich(raw_job)
    logger.info(
        "New job: %s at %s (%s) — categories: %s",
        job["title"], job["company_name"], job["ats"],
        ", ".join(job.get("categories", [])) or "uncategorized",
    )
    try:
        await send_slack_notification(job, "Tailoring disabled — test run", Path("none.pdf"))
    except Exception:
        logger.exception("Failed to send Slack notification for %s at %s", job["title"], job["company_name"])

    # --- Full pipeline (disabled for testing — restore when ready) ---
    # job = enrich(raw_job)
    # logger.info(
    #     "Processing: %s at %s (%s)",
    #     job["title"], job["company_name"], job["ats"],
    # )
    #
    # # --- Tailor ---
    # async with TAILOR_SEMAPHORE:
    #     try:
    #         tailoring_data, changes_text = await tailor_resume(job)
    #     except Exception:
    #         logger.exception("Failed to tailor resume for %s at %s", job["title"], job["company_name"])
    #         return
    #
    # # --- Generate PDF ---
    # pdf_path = None
    #
    # # Primary path: docx editing + LibreOffice conversion
    # if tailoring_data is not None:
    #     try:
    #         temp_docx = edit_docx(tailoring_data, job["company_slug"], job["job_id"])
    #         pdf_path = await convert_docx_to_pdf(temp_docx)
    #         # Clean up temp docx on success
    #         if pdf_path is not None and temp_docx.exists():
    #             temp_docx.unlink()
    #             logger.debug("Deleted temp docx: %s", temp_docx.name)
    #     except Exception:
    #         logger.exception(
    #             "Docx editing failed for %s at %s — falling back to ReportLab",
    #             job["title"], job["company_name"],
    #         )
    #
    # # Fallback: ReportLab PDF from plain text
    # if pdf_path is None:
    #     try:
    #         if tailoring_data is not None:
    #             plain_text = _build_plain_text_from_json(tailoring_data, _load_base_resume())
    #         else:
    #             plain_text = changes_text  # raw LLM output when JSON parse failed
    #         pdf_path = await generate_pdf_fallback(plain_text, job["company_slug"], job["job_id"])
    #     except Exception:
    #         logger.exception("Failed to generate PDF for %s at %s", job["title"], job["company_name"])
    #         return
    #
    # # --- Notify ---
    # try:
    #     await send_slack_notification(job, changes_text, pdf_path)
    # except Exception:
    #     logger.exception("Failed to send Slack notification for %s at %s", job["title"], job["company_name"])


async def process_new_jobs(raw_jobs: list[dict], ats: str) -> None:
    """Detect new jobs and process them concurrently (bounded by semaphore)."""
    new_jobs = await detect_new_jobs(raw_jobs, ats)
    if not new_jobs:
        return

    tasks = [asyncio.create_task(process_single_job(job)) for job in new_jobs]
    await asyncio.gather(*tasks, return_exceptions=True)


async def poll_all() -> tuple[list[dict], ...]:
    """Poll all ATS platforms concurrently and return their raw job lists."""
    return await asyncio.gather(
        poll_greenhouse(_greenhouse_slugs),
        poll_lever(_lever_slugs),
        poll_ashby(_ashby_slugs),
        poll_workday(_workday_companies),
        poll_smartrecruiters(_smartrecruiters_slugs),
        poll_custom(_custom_companies),
    )


_ATS_NAMES = ["greenhouse", "lever", "ashby", "workday", "smartrecruiters", "custom"]


async def run_jobright_cycle() -> None:
    logger.info("=== Starting Jobright cycle ===")

    since_ts = await _load_jobright_timestamp()
    jobs = await poll_jobright(since_timestamp=since_ts)

    # Apply seniority filter
    jobs = [j for j in jobs if is_intern_role(j["title"])]
    await _save_jobright_timestamp(jobs)
    logger.info("Jobright: %d jobs after seniority filter", len(jobs))

    # Dedup against DB
    new_jobs = await detect_new_jobs(jobs, "jobright")

    if not new_jobs:
        logger.info("=== Jobright cycle complete — no new jobs ===")
        return

    # Lazy apply URL resolution — only for new jobs
    logger.info("Resolving apply URLs for %d new Jobright jobs", len(new_jobs))
    which = asyncio.Semaphore(_RESOLVE_SEMAPHORE)
    async with httpx.AsyncClient() as client:
        async def resolve_one(job: dict) -> None:
            async with which:
                raw_id = job["job_id"].removeprefix("jobright_")
                job["apply_url"] = await resolve_apply_url(raw_id, client)

        await asyncio.gather(*[resolve_one(j) for j in new_jobs], return_exceptions=True)

    # Process new jobs through the pipeline
    await asyncio.gather(*(
        process_single_job(job) for job in new_jobs
    ), return_exceptions=True)

    logger.info("=== Jobright cycle complete ===")


async def run_seed() -> None:
    """Seed mode: poll everything, mark all current jobs as seen, then exit.

    No tailoring, no PDFs, no Slack notifications.  Run this once before
    starting the live monitor so only genuinely new postings trigger the
    pipeline.
    """
    logger.info("=== SEED MODE — marking all current jobs as seen ===")

    all_jobs = await poll_all()

    counts = {}
    for ats_name, jobs in zip(_ATS_NAMES, all_jobs):
        new = await detect_new_jobs(jobs, ats_name)
        counts[ats_name] = len(new)

    # Jobright
    jobright_jobs = await poll_jobright(since_timestamp=0)
    jobright_jobs = [j for j in jobright_jobs if is_intern_role(j["title"])]
    new_jobright = await detect_new_jobs(jobright_jobs, "jobright")
    counts["jobright"] = len(new_jobright)
    await _save_jobright_timestamp(jobright_jobs)
    logger.info("Jobright seed timestamp saved — live runs will only fetch jobs after this point")

    total = sum(counts.values())
    parts = " | ".join(f"{n.title()}: {c}" for n, c in counts.items())
    logger.info("Seed complete — marked %d jobs as seen (%s)", total, parts)
    logger.info("You can now run without --seed to start live monitoring.")


async def run_pipeline() -> None:
    """Run a single cycle of the full polling + processing pipeline."""
    logger.info("=== Starting pipeline run ===")

    all_jobs = await poll_all()

    await asyncio.gather(*(
        process_new_jobs(jobs, ats_name)
        for ats_name, jobs in zip(_ATS_NAMES, all_jobs)
    ))

    logger.info("=== Pipeline run complete ===")


async def main(seed: bool = False, discover: bool = False, no_discover: bool = False) -> None:
    logger.info("Initializing Persift")
    await init_db()

    try:
        # --- Company list loading ---
        # --discover: always run discovery fresh
        # --no-discover: skip freshness check, use existing files regardless of age
        # Otherwise: auto-run discovery if files are missing or older than 30 days
        if not no_discover and (discover or not _all_company_files_fresh()):
            if not discover:
                logger.info("Company list files missing or older than 30 days — running discovery")
            await _run_discovery()

        load_company_lists()

        total = sum(
            len(s) for s in (
                _greenhouse_slugs, _lever_slugs, _ashby_slugs,
                _workday_companies, _smartrecruiters_slugs,
                _custom_companies,
            )
        )
        if total == 0:
            logger.error(
                "No companies loaded. Run 'python discover_companies.py' first "
                "to build company lists from Common Crawl."
            )
            return

        # --- Seed mode ---
        if seed:
            await run_seed()
            return

        # --- Normal operation ---
        await run_pipeline()
        await run_jobright_cycle()
        await run_matching_cycle()
        await run_tailor_cycle()

        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            run_pipeline,
            "interval",
            minutes=POLL_INTERVAL_MINUTES,
            id="poll_cycle",
            max_instances=1,
        )
        scheduler.add_job(
            run_jobright_cycle,
            "interval",
            hours=1,
            id="jobright_cycle",
            max_instances=1,
        )
        scheduler.add_job(
            run_matching_cycle,
            "interval",
            minutes=6,
            id="matching_cycle",
            max_instances=1,
        )
        scheduler.add_job(
            run_tailor_cycle,
            "interval",
            minutes=10,
            id="tailor_cycle",
            max_instances=1,
        )
        scheduler.start()
        logger.info(
            "Scheduler started — Tier 1 every %d min, Jobright every 60 min, "
            "matching every 6 min, tailor every 10 min",
            POLL_INTERVAL_MINUTES,
        )

        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Shutting down")
            scheduler.shutdown()
    finally:
        await close_db()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Persift — internship monitor")
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Poll all ATS platforms and mark every current job as seen "
             "without tailoring or notifying. Run this once before starting "
             "live monitoring to avoid a flood of notifications.",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Force a fresh company discovery run via Common Crawl before "
             "starting, regardless of whether company files already exist.",
    )
    parser.add_argument(
        "--no-discover",
        action="store_true",
        dest="no_discover",
        help="Skip the company file freshness check and use existing files "
             "as-is, regardless of age. Useful when files are stale but "
             "discovery is not needed.",
    )
    args = parser.parse_args()
    asyncio.run(main(seed=args.seed, discover=args.discover, no_discover=args.no_discover))
