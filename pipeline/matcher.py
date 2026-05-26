"""Matching engine — pairs new jobs to active users.

Hard filters run in Python against in-memory user list (6 checks, O(jobs × users)).
Scoring runs in a thread pool so torch inference doesn't block the event loop.

Single public function: run_matching_cycle()
Intended cadence: every 6 minutes via APScheduler.
"""

import asyncio
import json
import logging

import httpx

from db import get_pool
from pipeline.notifier import notify_excluded_company
from pipeline.scorer import score_resume
from pollers.jobright import fetch_jd

logger = logging.getLogger(__name__)

_SCORE_THRESHOLD = 50
_JD_SEMAPHORE_SIZE = 5


async def _fetch_recent_jobs(conn) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT job_id, ats, company_slug, company_name, title,
               description, categories, work_model, h1b_sponsored,
               experience_level, location, apply_url
        FROM jobs
        WHERE first_seen_at > NOW() - INTERVAL '6 minutes'
        """
    )
    return [dict(r) for r in rows]


async def _fetch_active_users(conn) -> list[dict]:
    rows = await conn.fetch(
        "SELECT id, preferences, resume_text, work_auth, application_settings FROM users WHERE resume_text != ''"
    )
    result = []
    for r in rows:
        result.append({
            "id":                   r["id"],
            "preferences":          json.loads(r["preferences"]),
            "resume_text":          r["resume_text"],
            "work_auth":            json.loads(r["work_auth"]),
            "application_settings": json.loads(r["application_settings"]),
        })
    return result


def _passes_hard_filters(job: dict, user: dict) -> bool:
    prefs    = user["preferences"]
    work_auth = user["work_auth"]
    app      = user["application_settings"]

    # 1. Category match
    if not set(job["categories"]) & set(prefs.get("categories", [])):
        return False

    # 2. Work model match — Unknown passes through
    if job["work_model"] != "Unknown" and job["work_model"] not in set(prefs.get("work_models", [])):
        return False

    # 3. Sponsorship filter
    if work_auth.get("needs_sponsorship") and job["h1b_sponsored"] == "No":
        return False

    # 4. Job type match — absent/empty "job_types" means match all
    job_types = app.get("job_types", [])
    if job_types and job.get("experience_level") not in job_types:
        return False

    # 5. Location match — Remote always passes; On-Site/Hybrid checked against user locations
    if job["work_model"] not in ("Remote", "Unknown"):
        user_locations = app.get("locations", [])
        if user_locations:
            job_location = (job.get("location") or "").lower()
            if not any(loc.lower() in job_location for loc in user_locations):
                return False

    # 6. Blacklist — silently drop job; never surfaces to the user
    blacklisted = {s for s in app.get("blacklisted_companies", [])}
    if job["company_slug"] in blacklisted:
        return False

    return True


async def _fetch_jobright_jd(job: dict, client: httpx.AsyncClient, sem: asyncio.Semaphore) -> None:
    """Mutate job["description"] in place with fetched plain-text JD."""
    raw_id = job["job_id"].removeprefix("jobright_")
    async with sem:
        text = await fetch_jd(raw_id, client)
    if text:
        job["description"] = text


async def _bulk_insert_matches(conn, matches: list[dict], status: str = "queued") -> None:
    await conn.execute(
        """
        INSERT INTO user_jobs
            (user_id, job_id, job_ats, status, relevance_score, keyword_match_data)
        SELECT
            unnest($1::uuid[]),
            unnest($2::text[]),
            unnest($3::text[]),
            $6,
            unnest($4::smallint[]),
            unnest($5::text[])::jsonb
        ON CONFLICT (user_id, job_id, job_ats) DO NOTHING
        """,
        [m["user_id"]            for m in matches],
        [m["job_id"]             for m in matches],
        [m["job_ats"]            for m in matches],
        [m["relevance_score"]    for m in matches],
        [m["keyword_match_data"] for m in matches],
        status,
    )


async def run_matching_cycle() -> None:
    logger.info("=== Matching cycle starting ===")
    pool = get_pool()

    async with pool.acquire() as conn:
        jobs  = await _fetch_recent_jobs(conn)
        users = await _fetch_active_users(conn)

    if not jobs:
        logger.info("Matching cycle: no new jobs in last 6 minutes")
        return

    # Lazily fetch JDs for Jobright jobs that have no description in DB
    jobright_empty = [j for j in jobs if j["ats"] == "jobright" and not (j["description"] or "").strip()]
    if jobright_empty:
        logger.info("Fetching JDs for %d Jobright jobs", len(jobright_empty))
        jd_sem = asyncio.Semaphore(_JD_SEMAPHORE_SIZE)
        async with httpx.AsyncClient() as jd_client:
            await asyncio.gather(*[
                _fetch_jobright_jd(j, jd_client, jd_sem) for j in jobright_empty
            ])
        # Drop Jobright jobs that still have no description — nothing to score against
        jobs = [
            j for j in jobs
            if not (j["ats"] == "jobright" and not (j["description"] or "").strip())
        ]

    logger.info("Matching: %d new jobs × %d users", len(jobs), len(users))

    loop            = asyncio.get_running_loop()
    queued_matches: list[dict] = []
    notify_matches: list[dict] = []  # excluded companies — notify user, skip auto-apply
    below_threshold = 0

    for job in jobs:
        candidates = [u for u in users if _passes_hard_filters(job, u)]
        if not candidates:
            continue

        score_tasks = [
            loop.run_in_executor(None, score_resume, u["resume_text"], job["description"])
            for u in candidates
        ]
        results = await asyncio.gather(*score_tasks, return_exceptions=True)

        for user, result in zip(candidates, results):
            if isinstance(result, Exception):
                logger.warning(
                    "score_resume failed — user %s / job %s: %s",
                    user["id"], job["job_id"], result,
                )
                continue
            if result["relevance_score"] < _SCORE_THRESHOLD:
                below_threshold += 1
                continue

            app = user["application_settings"]
            excluded = {e["slug"]: e.get("reason", "") for e in app.get("excluded_companies", [])}

            match = {
                "user_id":            user["id"],
                "job_id":             job["job_id"],
                "job_ats":            job["ats"],
                "relevance_score":    result["relevance_score"],
                "keyword_match_data": json.dumps({
                    "present": result["present_keywords"],
                    "missing": result["missing_keywords"],
                }),
            }

            if job["company_slug"] in excluded:
                notify_matches.append({
                    **match,
                    "_job":    job,
                    "_user_id": str(user["id"]),
                    "_reason": excluded[job["company_slug"]],
                })
            else:
                queued_matches.append(match)

    async with pool.acquire() as conn:
        if queued_matches:
            await _bulk_insert_matches(conn, queued_matches, "queued")
        if notify_matches:
            await _bulk_insert_matches(conn, notify_matches, "notify_only")

    for nm in notify_matches:
        try:
            await notify_excluded_company(nm["_job"], nm["_user_id"], nm["_reason"])
        except Exception as exc:
            logger.warning("notify_excluded_company failed: %s", exc)

    logger.info(
        "Matching cycle done — %d queued, %d notify_only, %d below threshold (%d jobs, %d users)",
        len(queued_matches), len(notify_matches), below_threshold, len(jobs), len(users),
    )
