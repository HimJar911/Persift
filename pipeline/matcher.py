"""Matching engine — pairs new jobs to active users.

Hard filters run in Python against in-memory user list (3 checks, O(jobs × users)).
Scoring runs in a thread pool so torch inference doesn't block the event loop.

Single public function: run_matching_cycle()
Intended cadence: every 6 minutes via APScheduler.
"""

import asyncio
import json
import logging

from db import get_pool
from pipeline.scorer import score_resume

logger = logging.getLogger(__name__)

_SCORE_THRESHOLD = 50


async def _fetch_recent_jobs(conn) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT job_id, ats, company_slug, company_name, title,
               description, categories, work_model, h1b_sponsored
        FROM jobs
        WHERE first_seen_at > NOW() - INTERVAL '6 minutes'
        """
    )
    return [dict(r) for r in rows]


async def _fetch_active_users(conn) -> list[dict]:
    rows = await conn.fetch(
        "SELECT id, preferences, resume_text, work_auth FROM users WHERE resume_text != ''"
    )
    result = []
    for r in rows:
        result.append({
            "id":          r["id"],
            "preferences": json.loads(r["preferences"]),
            "resume_text": r["resume_text"],
            "work_auth":   json.loads(r["work_auth"]),
        })
    return result


def _passes_hard_filters(job: dict, user: dict) -> bool:
    prefs     = user["preferences"]
    work_auth = user["work_auth"]

    # 1. Category match
    if not set(job["categories"]) & set(prefs.get("categories", [])):
        return False

    # 2. Work model match — Unknown passes through
    if job["work_model"] != "Unknown" and job["work_model"] not in set(prefs.get("work_models", [])):
        return False

    # 3. Sponsorship filter
    if work_auth.get("needs_sponsorship") and job["h1b_sponsored"] == "No":
        return False

    return True


async def _bulk_insert_matches(conn, matches: list[dict]) -> None:
    await conn.execute(
        """
        INSERT INTO user_jobs
            (user_id, job_id, job_ats, status, relevance_score, keyword_match_data)
        SELECT
            unnest($1::uuid[]),
            unnest($2::text[]),
            unnest($3::text[]),
            'queued',
            unnest($4::smallint[]),
            unnest($5::text[])::jsonb
        ON CONFLICT (user_id, job_id, job_ats) DO NOTHING
        """,
        [m["user_id"]           for m in matches],
        [m["job_id"]            for m in matches],
        [m["job_ats"]           for m in matches],
        [m["relevance_score"]   for m in matches],
        [m["keyword_match_data"] for m in matches],
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

    logger.info("Matching: %d new jobs × %d users", len(jobs), len(users))

    loop         = asyncio.get_running_loop()
    matches:     list[dict] = []
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
            matches.append({
                "user_id":           user["id"],
                "job_id":            job["job_id"],
                "job_ats":           job["ats"],
                "relevance_score":   result["relevance_score"],
                "keyword_match_data": json.dumps({
                    "present": result["present_keywords"],
                    "missing": result["missing_keywords"],
                }),
            })

    if matches:
        async with pool.acquire() as conn:
            await _bulk_insert_matches(conn, matches)

    logger.info(
        "Matching cycle done — %d queued, %d below threshold (%d jobs, %d users)",
        len(matches), below_threshold, len(jobs), len(users),
    )
