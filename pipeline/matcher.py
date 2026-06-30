"""Matching engine — pairs new jobs to active users.

Hard filters run in Python against in-memory user list (6 checks, O(jobs × users)).
Scoring runs in a thread pool so torch inference doesn't block the event loop.

Single public function: run_matching_cycle()
Intended cadence: every 6 minutes via APScheduler.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

import httpx

from config import PIPELINE_VERSION, SCORER_MODEL_VERSION
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
               experience_level, location, apply_url, posted_at
        FROM jobs
        WHERE first_seen_at > NOW() - INTERVAL '6 minutes'
        """
    )
    return [dict(r) for r in rows]


async def _fetch_active_users(conn) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT id, tier, preferences, resume_text, work_auth, application_settings
        FROM users WHERE resume_text != ''
        """
    )
    result = []
    for r in rows:
        work_auth = json.loads(r["work_auth"])
        app       = json.loads(r["application_settings"])
        # ML/profile attributes are sourced from the application_settings JSONB
        # (single source of truth — written by the signup API and update_profile.py).
        # The legacy top-level columns (requires_sponsorship/work_auth_type/university/
        # graduation_date/major) are never populated for API-created users, so we
        # derive these from JSONB instead. See ARCHITECTURE.md "profile data location".
        result.append({
            "id":                   r["id"],
            "tier":                 r["tier"],
            "preferences":          json.loads(r["preferences"]),
            "resume_text":          r["resume_text"],
            "work_auth":            work_auth,
            "application_settings": app,
            "requires_sponsorship": app.get("needs_sponsorship", work_auth.get("needs_sponsorship")),
            "work_auth_type":       app.get("visa_type"),
            "university":           app.get("school"),
            "graduation_date":      app.get("graduation_date"),
            "major":                app.get("major"),
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
    """Bulk unnest insert — used for notify_only matches where RETURNING id is not needed."""
    await conn.execute(
        """
        INSERT INTO user_jobs
            (user_id, job_id, job_ats, status, relevance_score, keyword_match_data,
             jd_text_snapshot, user_profile_snapshot, days_since_posting,
             hour_submitted, day_of_week, submission_mode)
        SELECT
            unnest($1::uuid[]),
            unnest($2::text[]),
            unnest($3::text[]),
            $6,
            unnest($4::smallint[]),
            unnest($5::text[])::jsonb,
            unnest($7::text[]),
            unnest($8::text[])::jsonb,
            unnest($9::int[]),
            unnest($10::smallint[]),
            unnest($11::smallint[]),
            unnest($12::text[])
        ON CONFLICT (user_id, job_id, job_ats) DO NOTHING
        """,
        [m["user_id"]                                          for m in matches],
        [m["job_id"]                                           for m in matches],
        [m["job_ats"]                                          for m in matches],
        [m["relevance_score"]                                  for m in matches],
        [m["keyword_match_data"]                               for m in matches],
        status,
        [m.get("jd_text_snapshot")                             for m in matches],
        [json.dumps(m.get("user_profile_snapshot") or {})      for m in matches],
        [m.get("days_since_posting")                           for m in matches],
        [m.get("hour_submitted")                               for m in matches],
        [m.get("day_of_week")                                  for m in matches],
        [m.get("submission_mode")                              for m in matches],
    )


def _build_user_profile_snapshot(user: dict) -> dict:
    """Snapshot of user profile state at match time for ML training."""
    return {
        "tier":                  user.get("tier"),
        "requires_sponsorship":  user.get("requires_sponsorship"),
        "work_auth_type":        user.get("work_auth_type"),
        "university":            user.get("university"),
        "graduation_date":       str(user.get("graduation_date")) if user.get("graduation_date") else None,
        "major":                 user.get("major"),
        "categories":            user.get("preferences", {}).get("categories", []),
        "work_models":           user.get("preferences", {}).get("work_models", []),
        "resume_length_chars":   len(user.get("resume_text") or ""),
        "snapshot_at":           datetime.now(timezone.utc).isoformat(),
    }


def _calculate_days_since_posting(posted_at_ms: int) -> int | None:
    """Calculate days between job posting and now."""
    if not posted_at_ms or posted_at_ms == 0:
        return None
    posted = datetime.fromtimestamp(posted_at_ms / 1000, tz=timezone.utc)
    delta = datetime.now(timezone.utc) - posted
    return max(0, delta.days)


async def _insert_queued_match_with_prediction(conn, match: dict) -> None:
    """Insert one queued user_jobs row (RETURNING id) then log to model_predictions.

    model_predictions insert is wrapped in try/except — failure logs a WARNING
    but never blocks the match.
    """
    row = await conn.fetchrow(
        """
        INSERT INTO user_jobs
            (user_id, job_id, job_ats, status, relevance_score, keyword_match_data,
             jd_text_snapshot, user_profile_snapshot, days_since_posting,
             hour_submitted, day_of_week, submission_mode)
        VALUES ($1, $2, $3, 'queued', $4, $5::jsonb, $6, $7::jsonb, $8, $9, $10, $11)
        ON CONFLICT (user_id, job_id, job_ats) DO NOTHING
        RETURNING id
        """,
        match["user_id"],
        match["job_id"],
        match["job_ats"],
        match["relevance_score"],
        match["keyword_match_data"],
        match.get("jd_text_snapshot"),
        json.dumps(match.get("user_profile_snapshot") or {}),
        match.get("days_since_posting"),
        match.get("hour_submitted"),
        match.get("day_of_week"),
        match.get("submission_mode"),
    )

    if row is None:
        # ON CONFLICT — duplicate, skip prediction
        return

    user_job_id = row["id"]
    score       = match["relevance_score"]

    feature_snapshot = {
        "relevance_score":    score,
        "keyword_match":      json.loads(match["keyword_match_data"]),
        "job_categories":     match.get("job_categories", []),
        "job_work_model":     match.get("job_work_model"),
        "job_experience_level": match.get("job_experience_level"),
        "days_since_posting": match.get("days_since_posting"),
        "hour_submitted":     match.get("hour_submitted"),
        "day_of_week":        match.get("day_of_week"),
        "user_tier":          match.get("user_tier"),
        "requires_sponsorship": match.get("requires_sponsorship"),
        "tailoring_eligible": score >= 80,
        "pipeline_version":   PIPELINE_VERSION,
    }

    prediction_id = None
    try:
        pred_row = await conn.fetchrow(
            """
            INSERT INTO model_predictions
                (user_job_id, predicted_at, model_version,
                 callback_probability, predicted_stage, feature_snapshot)
            VALUES ($1, NOW(), $2, $3, 'callback', $4::jsonb)
            RETURNING id
            """,
            user_job_id,
            SCORER_MODEL_VERSION,
            round(score / 100.0, 4),
            json.dumps(feature_snapshot),
        )
        prediction_id = pred_row["id"] if pred_row else None
    except Exception as exc:
        logger.warning(
            "model_predictions insert failed for user_job_id=%s: %s", user_job_id, exc
        )

    logger.debug(
        "Match logged: user=%s job=%s score=%s prediction_id=%s",
        match["user_id"], match["job_id"], score, prediction_id,
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

            now_utc            = datetime.now(timezone.utc)
            days_since_posting = _calculate_days_since_posting(job.get("posted_at", 0))
            auto_submit        = app.get("auto_submit", False)

            match = {
                "user_id":            user["id"],
                "job_id":             job["job_id"],
                "job_ats":            job["ats"],
                "relevance_score":    result["relevance_score"],
                "keyword_match_data": json.dumps({
                    "present": result["present_keywords"],
                    "missing": result["missing_keywords"],
                }),
                # ML snapshot fields
                "jd_text_snapshot":      job.get("description") or "",
                "user_profile_snapshot": _build_user_profile_snapshot(user),
                "days_since_posting":    days_since_posting,
                "hour_submitted":        now_utc.hour,
                "day_of_week":           now_utc.weekday(),
                "submission_mode":       "autonomous" if auto_submit else "review_before_submit",
                # Feature fields for model_predictions (queued path only)
                "job_categories":        list(job.get("categories") or []),
                "job_work_model":        job.get("work_model"),
                "job_experience_level":  job.get("experience_level"),
                "user_tier":             user.get("tier"),
                "requires_sponsorship":  user.get("requires_sponsorship"),
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
        for m in queued_matches:
            await _insert_queued_match_with_prediction(conn, m)
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


if __name__ == "__main__":
    import argparse
    from db import init_db, close_db

    ap = argparse.ArgumentParser(description="Run one matcher cycle and report user_jobs created.")
    ap.add_argument(
        "--window",
        default="24 hours",
        metavar="INTERVAL",
        help="SQL interval for job lookback (default: '24 hours'). Normal cadence is '6 minutes'.",
    )
    ap.add_argument(
        "--all",
        action="store_true",
        dest="match_all",
        help="Match against ALL jobs in the DB — no first_seen_at filter. Local testing only.",
    )
    _cli = ap.parse_args()

    # Patch _fetch_recent_jobs at module scope so run_matching_cycle() picks it up.
    # Assigned here (not inside the async fn) so it lands in the module's global dict.
    if _cli.match_all:
        async def _fetch_recent_jobs(conn):  # noqa: F811
            rows = await conn.fetch(
                """
                SELECT job_id, ats, company_slug, company_name, title,
                       description, categories, work_model, h1b_sponsored,
                       experience_level, location, apply_url, posted_at
                FROM jobs
                """
            )
            return [dict(r) for r in rows]
    else:
        _cli_window = _cli.window

        async def _windowed_fetch(conn):
            rows = await conn.fetch(
                f"""
                SELECT job_id, ats, company_slug, company_name, title,
                       description, categories, work_model, h1b_sponsored,
                       experience_level, location, apply_url, posted_at
                FROM jobs
                WHERE first_seen_at > NOW() - INTERVAL '{_cli_window}'
                """
            )
            return [dict(r) for r in rows]

        _fetch_recent_jobs = _windowed_fetch  # replaces the module global

    async def _run():
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        await init_db()
        try:
            pool = get_pool()
            async with pool.acquire() as conn:
                before = await conn.fetchval("SELECT COUNT(*) FROM user_jobs")

            await run_matching_cycle()

            async with pool.acquire() as conn:
                after = await conn.fetchval("SELECT COUNT(*) FROM user_jobs")

            print(f"\nuser_jobs created: {after - before}  (before={before}, after={after})")
        finally:
            await close_db()

    asyncio.run(_run())
