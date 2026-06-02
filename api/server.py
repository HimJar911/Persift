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
    work_auth            = json.dumps({"needs_sponsorship": needs_sponsorship})
    application_settings = json.dumps({
        "excluded_companies":  excluded_list,
        "blacklisted_companies": blacklisted_list,
    })

    pool = get_pool()
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO users (email, tier, preferences, resume_text, work_auth, application_settings)
                VALUES ($1, $2, $3::jsonb, $4, $5::jsonb, $6::jsonb)
                RETURNING id
                """,
                email, tier, preferences, resume_text, work_auth, application_settings,
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


class _AppliedReq(BaseModel):
    user_id: str
    job_ats: str


class _FailedReq(BaseModel):
    user_id: str
    job_ats: str
    reason: str = ""
    failure_stage: str | None = None


@app.get("/users/{user_id}")
async def get_user_profile(user_id: str):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT email,
                   COALESCE(application_settings->>'first_name',   '') AS first_name,
                   COALESCE(application_settings->>'last_name',    '') AS last_name,
                   COALESCE(application_settings->>'phone',        '') AS phone,
                   COALESCE(application_settings->>'linkedin_url', '') AS linkedin_url,
                   COALESCE(application_settings->>'location_city','') AS location_city
            FROM users WHERE id = $1::uuid
            """,
            user_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    return dict(row)


@app.get("/jobs/queue")
async def get_job_queue(
    user_id: str = Query(...),
    limit: int = Query(default=1, ge=1, le=20),
):
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                j.job_id, j.ats AS job_ats, j.apply_url, j.company_name, j.title,
                u.email,
                COALESCE(u.application_settings->>'first_name', '') AS first_name,
                COALESCE(u.application_settings->>'last_name',  '') AS last_name,
                COALESCE(u.application_settings->>'phone',       '') AS phone,
                COALESCE(u.application_settings->>'linkedin_url','') AS linkedin_url,
                COALESCE(u.application_settings->>'location_city','') AS location_city
            FROM user_jobs uj
            JOIN jobs  j ON j.job_id = uj.job_id AND j.ats = uj.job_ats
            JOIN users u ON u.id = uj.user_id
            WHERE uj.user_id = $1::uuid AND uj.status = 'applying'
            ORDER BY uj.created_at ASC
            LIMIT $2
            """,
            user_id, limit,
        )
    jobs = [dict(r) for r in rows]
    return {"jobs": jobs}


@app.get("/jobs/queue/count")
async def get_queue_count(user_id: str = Query(...)):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) AS count FROM user_jobs WHERE user_id = $1::uuid AND status = 'applying'",
            user_id,
        )
    return {"count": row["count"] if row else 0}


@app.post("/jobs/{job_id}/applied")
async def mark_applied(job_id: str, body: _AppliedReq):
    pool = get_pool()
    async with pool.acquire() as conn:
        tag = await conn.execute(
            """
            UPDATE user_jobs SET status = 'applied', updated_at = NOW()
            WHERE user_id = $1::uuid AND job_id = $2 AND job_ats = $3
            """,
            body.user_id, job_id, body.job_ats,
        )
    if int(tag.split()[-1]) == 0:
        raise HTTPException(status_code=404, detail="user_job not found")

    async with pool.acquire() as conn:
        user_job_id = await conn.fetchval(
            "SELECT id FROM user_jobs WHERE user_id = $1::uuid AND job_id = $2 AND job_ats = $3",
            body.user_id, job_id, body.job_ats,
        )

        try:
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
        except Exception as e:
            logger.warning(
                "Failed to insert applied_confirmed outcome for user_job %s: %s",
                user_job_id, e,
            )

        try:
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
        except Exception as e:
            logger.warning(
                "Failed to update model_predictions for user_job %s: %s",
                user_job_id, e,
            )

    logger.debug(
        "Application confirmed: user_job=%s outcome=applied_confirmed", user_job_id
    )
    return {"ok": True}


@app.post("/jobs/{job_id}/failed")
async def mark_failed(job_id: str, body: _FailedReq):
    pool = get_pool()
    async with pool.acquire() as conn:
        tag = await conn.execute(
            """
            UPDATE user_jobs SET status = 'failed', updated_at = NOW()
            WHERE user_id = $1::uuid AND job_id = $2 AND job_ats = $3
            """,
            body.user_id, job_id, body.job_ats,
        )
    if int(tag.split()[-1]) == 0:
        raise HTTPException(status_code=404, detail="user_job not found")

    failure_reason = body.reason
    failure_stage  = body.failure_stage

    async with pool.acquire() as conn:
        user_job_id = await conn.fetchval(
            "SELECT id FROM user_jobs WHERE user_id = $1::uuid AND job_id = $2 AND job_ats = $3",
            body.user_id, job_id, body.job_ats,
        )

        try:
            retry_count = await conn.fetchval(
                "SELECT retry_count FROM user_jobs WHERE id = $1",
                user_job_id,
            )
            await conn.execute(
                """
                INSERT INTO application_attempts (
                    user_job_id, attempt_number, started_at, ended_at,
                    success, failure_stage, error_details, created_at
                ) VALUES ($1, $2, NOW(), NOW(), FALSE, $3, $4::jsonb, NOW())
                """,
                user_job_id,
                (retry_count or 0) + 1,
                failure_stage,
                json.dumps({"reason": failure_reason}),
            )
        except Exception as e:
            logger.warning(
                "Failed to insert application_attempt for user_job %s: %s",
                user_job_id, e,
            )

        try:
            await conn.execute(
                """
                INSERT INTO application_outcomes (
                    user_job_id, outcome_type, outcome_date, outcome_source,
                    confidence, previous_outcome_type, outcome_metadata, created_at
                )
                SELECT $1, 'rejected', NOW(), 'extension_detected',
                       1.0, current_stage, $2::jsonb, NOW()
                FROM user_jobs
                WHERE id = $1
                """,
                user_job_id,
                json.dumps({"failure_reason": failure_reason, "failure_stage": failure_stage}),
            )
        except Exception as e:
            logger.warning(
                "Failed to insert failed outcome for user_job %s: %s",
                user_job_id, e,
            )

    logger.debug(
        "Application failed: user_job=%s stage=%s reason=%s",
        user_job_id, failure_stage, failure_reason,
    )
    return {"ok": True}


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

    if row is None or row["status"] != "applying":
        raise HTTPException(status_code=404, detail="Resume not found or job not in applying state")

    safe_id  = job_id.replace("/", "_")
    pdf_path = RESUMES_DIR / user_id / f"{safe_id}_{job_ats}_tailored.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found")

    return FileResponse(str(pdf_path), media_type="application/pdf")
