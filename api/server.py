"""Persift API server."""

import io
import json
import logging
from contextlib import asynccontextmanager
from datetime import timezone
from pathlib import Path

import pdfplumber
from asyncpg import UniqueViolationError
from docx import Document
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from db import close_db, get_pool, init_db

logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent.parent
RESUMES_DIR = PROJECT_DIR / "outputs" / "resumes"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()


app = FastAPI(title="Persift API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _extract_docx_text(content: bytes) -> str:
    doc = Document(io.BytesIO(content))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _extract_pdf_text(content: bytes) -> str:
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/users", status_code=201)
async def create_user(
    email: str = Form(...),
    tier: str = Form(default="free"),
    resume: UploadFile = File(...),
    categories: str = Form(...),
    work_models: str = Form(...),
    needs_sponsorship: bool = Form(...),
    excluded_companies: str = Form(default="[]"),
    blacklisted_companies: str = Form(default=""),
):
    if tier not in ("free", "pro"):
        raise HTTPException(status_code=400, detail="tier must be 'free' or 'pro'")

    suffix = Path(resume.filename or "").suffix.lower()
    if suffix not in (".docx", ".pdf"):
        raise HTTPException(status_code=400, detail="Resume must be .docx or .pdf")

    content = await resume.read()

    resume_text = _extract_docx_text(content) if suffix == ".docx" else _extract_pdf_text(content)

    categories_list  = [c.strip() for c in categories.split(",")  if c.strip()]
    work_models_list = [w.strip() for w in work_models.split(",") if w.strip()]

    try:
        excluded_list = json.loads(excluded_companies)
        if not isinstance(excluded_list, list):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="excluded_companies must be a JSON array")

    blacklisted_list = [s.strip() for s in blacklisted_companies.split(",") if s.strip()]

    preferences          = json.dumps({"categories": categories_list, "work_models": work_models_list})
    # needs_sponsorship is now a COLUMN (field-home migration 016), not work_auth JSONB.
    application_settings = json.dumps({
        "excluded_companies":  excluded_list,
        "blacklisted_companies": blacklisted_list,
    })

    pool = get_pool()
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO users (email, tier, preferences, resume_text, needs_sponsorship, application_settings)
                VALUES ($1, $2, $3::jsonb, $4, $5, $6::jsonb)
                RETURNING id
                """,
                email, tier, preferences, resume_text, needs_sponsorship, application_settings,
            )
    except UniqueViolationError:
        raise HTTPException(status_code=409, detail="Email already registered")
    except Exception:
        logger.exception("DB error creating user %s", email)
        raise HTTPException(status_code=500, detail="Database error")

    user_id = row["id"]

    resume_dir = RESUMES_DIR / str(user_id)
    resume_dir.mkdir(parents=True, exist_ok=True)
    (resume_dir / f"base_resume{suffix}").write_bytes(content)

    return JSONResponse(status_code=201, content={"user_id": str(user_id)})


class _SubmittedReq(BaseModel):
    user_id: str
    job_ats: str
    # Field Correction two-snapshot payload — present ONLY when review was on
    # (submission_mode='review'). Raw snapshots; the server derives the diff.
    snapshot_filled: dict | None = None      # #1: what Persift filled
    snapshot_submitted: dict | None = None   # #2: what the user submitted


class _AwaitingReviewReq(BaseModel):
    user_id: str
    job_ats: str
    reason: str = ""


class _ReleasedReq(BaseModel):
    user_id: str
    job_ats: str
    reason: str = ""              # mechanical/user reason (axis C), NOT an outcome
    failure_stage: str | None = None


# Retry cap shared by user-skip and mechanical death (lifecycle §Mechanism 3).
_RETRY_CAP = 2


@app.get("/users/{user_id}")
async def get_user_profile(user_id: str):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT email,
                   COALESCE(application_settings->>'first_name',      '') AS first_name,
                   COALESCE(application_settings->>'last_name',       '') AS last_name,
                   COALESCE(application_settings->>'phone',           '') AS phone,
                   COALESCE(application_settings->>'linkedin_url',    '') AS linkedin_url,
                   -- location_city/state now COLUMNS (field-home migration 016)
                   COALESCE(location_city,  '') AS location_city,
                   COALESCE(location_state, '') AS location_state,
                   COALESCE(application_settings->>'location_country','') AS location_country,
                   COALESCE(application_settings->>'github_url',      '') AS github_url,
                   COALESCE(application_settings->>'preferred_name',  '') AS preferred_name,
                   -- university/major/gpa/graduation_date now COLUMNS. Aliased back to
                   -- the extension's expected keys (school, etc.). graduation_date is a
                   -- DATE column; render as 'Mon YYYY' free-text for the filler (per
                   -- store-canonical/render-per-form; filler reformats as each form needs).
                   COALESCE(university, '') AS school,
                   COALESCE(application_settings->>'degree', '') AS degree,
                   COALESCE(major, '') AS major,
                   COALESCE(gpa::text, '') AS gpa,
                   COALESCE(to_char(graduation_date, 'FMMonth YYYY'), '') AS graduation_date,
                   COALESCE(application_settings->>'eeo_gender',      '') AS eeo_gender,
                   COALESCE(application_settings->>'eeo_race',        '') AS eeo_race,
                   COALESCE((application_settings->>'eeo_hispanic')::boolean::text, 'false') AS eeo_hispanic,
                   COALESCE(application_settings->>'eeo_veteran',     '') AS eeo_veteran,
                   COALESCE(application_settings->>'eeo_disability',  '') AS eeo_disability,
                   COALESCE((application_settings->>'work_authorized')::boolean::text, 'true') AS work_authorized,
                   -- needs_sponsorship/visa_type now COLUMNS
                   COALESCE(needs_sponsorship::text, 'false') AS needs_sponsorship,
                   COALESCE(visa_type, 'OTHER') AS visa_type,
                   COALESCE((application_settings->>'desired_hourly_min')::int, 0) AS desired_hourly_min,
                   COALESCE((application_settings->>'desired_hourly_max')::int, 0) AS desired_hourly_max,
                   COALESCE(application_settings->'custom_answers', '[]'::jsonb)::text AS custom_answers,
                   COALESCE(application_settings->'previous_employers', '[]'::jsonb)::text AS previous_employers
            FROM users WHERE id = $1::uuid
            """,
            user_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    result = dict(row)
    import json
    result['custom_answers'] = json.loads(result['custom_answers'])
    result['previous_employers'] = json.loads(result['previous_employers'])
    return result


class _ClaimReq(BaseModel):
    user_id: str


# Lease duration for a claimed application (lifecycle Mechanism 2). A submitting
# row whose lease_expires_at is in the past is dead and gets reaped by cleanup.
_LEASE_MINUTES = 10


@app.post("/jobs/claim")
async def claim_job(body: _ClaimReq):
    """Atomically claim the next 'ready' application for this user.

    Read+write in ONE statement (UPDATE ... RETURNING with FOR UPDATE SKIP
    LOCKED) so only one caller can ever win a given row — closes the
    read-then-act gap that let two pollers double-apply. Moves ready ->
    submitting and stamps the lease. Replaces the old GET /jobs/queue.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE user_jobs uj
            SET status = 'submitting',
                lease_expires_at = NOW() + ($2 || ' minutes')::interval,
                updated_at = NOW()
            WHERE uj.id = (
                SELECT id FROM user_jobs
                WHERE user_id = $1::uuid AND status = 'ready'
                ORDER BY created_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            RETURNING uj.id, uj.job_id, uj.job_ats
            """,
            body.user_id, str(_LEASE_MINUTES),
        )

    if row is None:
        return {"job": None}

    # Second read joins job + profile carry-along for the extension to fill with.
    async with pool.acquire() as conn:
        detail = await conn.fetchrow(
            """
            SELECT
                j.job_id, j.ats AS job_ats, j.apply_url, j.company_name, j.title,
                u.email,
                COALESCE(u.application_settings->>'first_name', '') AS first_name,
                COALESCE(u.application_settings->>'last_name',  '') AS last_name,
                COALESCE(u.application_settings->>'phone',       '') AS phone,
                COALESCE(u.application_settings->>'linkedin_url','') AS linkedin_url,
                u.location_city
            FROM jobs  j
            JOIN users u ON u.id = $1::uuid
            WHERE j.job_id = $2 AND j.ats = $3
            """,
            body.user_id, row["job_id"], row["job_ats"],
        )
    return {"job": dict(detail) if detail else None}


class _HeartbeatReq(BaseModel):
    user_id: str
    job_ats: str


@app.post("/jobs/{job_id}/heartbeat")
async def heartbeat(job_id: str, body: _HeartbeatReq):
    """Renew the lease on a submitting job so cleanup won't reap it while the
    extension is actively filling. submitting -> submitting (lease bumped)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        tag = await conn.execute(
            """
            UPDATE user_jobs
            SET lease_expires_at = NOW() + ($4 || ' minutes')::interval,
                updated_at = NOW()
            WHERE user_id = $1::uuid AND job_id = $2 AND job_ats = $3
              AND status = 'submitting'
            """,
            body.user_id, job_id, body.job_ats, str(_LEASE_MINUTES),
        )
    if int(tag.split()[-1]) == 0:
        raise HTTPException(
            status_code=404, detail="user_job not found or not in submitting state"
        )
    return {"ok": True}


@app.get("/jobs/queue/count")
async def get_queue_count(user_id: str = Query(...)):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) AS count FROM user_jobs WHERE user_id = $1::uuid AND status = 'ready'",
            user_id,
        )
    return {"count": row["count"] if row else 0}


@app.post("/jobs/{job_id}/submitted")
async def mark_submitted(job_id: str, body: _SubmittedReq):
    """Confirm a submitted application. Fat endpoint (one transaction):

    - status: submitting -> submitted (auto) OR awaiting_review -> submitted (review).
    - outcome: append applied_confirmed (the ONLY type extension_detected may write).
    - field_corrections: if snapshots present (review was on), insert both raw
      snapshots; the diff is derived later/server-side.
    - model_predictions: mark the prediction evaluated.

    All-or-nothing so we never record a submit without its corrections, or vice
    versa. Terminal for `status` — hands off to the Outcome entity.
    """
    has_snapshots = body.snapshot_filled is not None and body.snapshot_submitted is not None
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            user_job_id = await conn.fetchval(
                """
                UPDATE user_jobs SET status = 'submitted', updated_at = NOW()
                WHERE user_id = $1::uuid AND job_id = $2 AND job_ats = $3
                  AND status IN ('submitting', 'awaiting_review')
                RETURNING id
                """,
                body.user_id, job_id, body.job_ats,
            )
            if user_job_id is None:
                raise HTTPException(
                    status_code=404,
                    detail="user_job not found or not in submitting/awaiting_review state",
                )

            # applied_confirmed — the one fact the browser directly witnesses.
            await conn.execute(
                """
                INSERT INTO application_outcomes (
                    user_job_id, outcome_type, outcome_date, outcome_source,
                    confidence, previous_outcome_type, created_at
                )
                SELECT $1, 'applied_confirmed', NOW(), 'extension_detected',
                       1.0, current_stage, NOW()
                FROM user_jobs
                WHERE id = $1
                """,
                user_job_id,
            )

            # Field Correction — only when review was on (snapshots supplied).
            if has_snapshots:
                await conn.execute(
                    """
                    INSERT INTO field_corrections (
                        user_job_id, snapshot_filled, snapshot_submitted
                    ) VALUES ($1, $2::jsonb, $3::jsonb)
                    """,
                    user_job_id,
                    json.dumps(body.snapshot_filled),
                    json.dumps(body.snapshot_submitted),
                )

            await conn.execute(
                """
                UPDATE model_predictions
                SET actual_outcome_type = 'applied_confirmed',
                    actual_outcome_date = NOW(),
                    evaluated_at = NOW()
                WHERE id = (
                    SELECT id FROM model_predictions
                    WHERE user_job_id = $1 AND actual_outcome_type IS NULL
                    ORDER BY predicted_at DESC
                    LIMIT 1
                )
                """,
                user_job_id,
            )

    logger.debug(
        "Application submitted: user_job=%s corrections=%s", user_job_id, has_snapshots
    )
    return {"ok": True}


@app.post("/jobs/{job_id}/awaiting_review")
async def mark_awaiting_review(job_id: str, body: _AwaitingReviewReq):
    """Fill done, auto-submit OFF: park for the user to review & submit.
    submitting -> awaiting_review. Exits via POST /jobs/{id}/submitted."""
    pool = get_pool()
    async with pool.acquire() as conn:
        tag = await conn.execute(
            """
            UPDATE user_jobs SET status = 'awaiting_review', updated_at = NOW()
            WHERE user_id = $1::uuid AND job_id = $2 AND job_ats = $3
              AND status = 'submitting'
            """,
            body.user_id, job_id, body.job_ats,
        )
    if int(tag.split()[-1]) == 0:
        raise HTTPException(
            status_code=404, detail="user_job not found or not in submitting state"
        )
    logger.debug("awaiting_review: job=%s reason=%s", job_id, body.reason)
    return {"ok": True}


@app.post("/jobs/{job_id}/released")
async def mark_released(job_id: str, body: _ReleasedReq):
    """Client voluntarily gives up a claim it can't finish (skip, or a clean
    in-client failure). Replaces the old /failed.

    - retry_count < cap: submitting -> ready (retryable; artifact still good, no
      re-tailor). Re-served on the next claim. retry_count += 1.
    - retry_count >= cap: submitting -> abandoned (terminal); failure_reason set.

    Writes an application_attempt (mechanical tracking) but NEVER an outcome —
    mechanical/user non-completion is axis C (failure_reason), not axis B
    (employer verdict). This is the bug #3 fix: /failed no longer fabricates
    'rejected' outcomes. Server-side cleanup, not this endpoint, reaps
    lease-expired rows (submitting -> abandoned)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT id, retry_count FROM user_jobs
                WHERE user_id = $1::uuid AND job_id = $2 AND job_ats = $3
                  AND status = 'submitting'
                FOR UPDATE
                """,
                body.user_id, job_id, body.job_ats,
            )
            if row is None:
                raise HTTPException(
                    status_code=404,
                    detail="user_job not found or not in submitting state",
                )
            user_job_id = row["id"]
            new_retry = (row["retry_count"] or 0) + 1
            terminal = new_retry > _RETRY_CAP

            if terminal:
                await conn.execute(
                    """
                    UPDATE user_jobs
                    SET status = 'abandoned', retry_count = $2,
                        failure_reason = $3, lease_expires_at = NULL, updated_at = NOW()
                    WHERE id = $1
                    """,
                    user_job_id, new_retry, body.reason or None,
                )
            else:
                await conn.execute(
                    """
                    UPDATE user_jobs
                    SET status = 'ready', retry_count = $2,
                        lease_expires_at = NULL, updated_at = NOW()
                    WHERE id = $1
                    """,
                    user_job_id, new_retry,
                )

            await conn.execute(
                """
                INSERT INTO application_attempts (
                    user_job_id, attempt_number, started_at, ended_at,
                    success, failure_stage, error_details, created_at
                ) VALUES ($1, $2, NOW(), NOW(), FALSE, $3, $4::jsonb, NOW())
                """,
                user_job_id, new_retry, body.failure_stage,
                json.dumps({"reason": body.reason}),
            )

    logger.debug(
        "Application released: user_job=%s retry=%d terminal=%s reason=%s",
        user_job_id, new_retry, terminal, body.reason,
    )
    return {"ok": True, "terminal": terminal, "retry_count": new_retry}


_ALLOWED_DOC_TYPES = {"transcript_undergrad", "transcript_grad"}

@app.get("/users/{user_id}/documents/{doc_type}")
async def get_user_document(user_id: str, doc_type: str):
    if doc_type not in _ALLOWED_DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown doc_type: {doc_type}")
    pdf_path = RESUMES_DIR / user_id / f"{doc_type}.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    return FileResponse(str(pdf_path), media_type="application/pdf")


@app.get("/jobs/{job_id}/resume")
async def get_tailored_resume(
    job_id: str,
    job_ats: str = Query(...),
    user_id: str = Query(...),
):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT status FROM user_jobs
            WHERE user_id = $1::uuid AND job_id = $2 AND job_ats = $3
            """,
            user_id, job_id, job_ats,
        )

    if row is None or row["status"] not in ("ready", "submitting"):
        raise HTTPException(status_code=404, detail="Resume not found or job not in ready/submitting state")

    safe_id  = job_id.replace("/", "_")
    pdf_path = RESUMES_DIR / user_id / f"{safe_id}_{job_ats}_tailored.pdf"
    if not pdf_path.exists():
        base_pdf = RESUMES_DIR / user_id / "base_resume.pdf"
        if base_pdf.exists():
            pdf_path = base_pdf
        else:
            raise HTTPException(status_code=404, detail="PDF file not found")

    return FileResponse(str(pdf_path), media_type="application/pdf")
