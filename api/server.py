"""Persift API server."""

import io
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import pdfplumber
from asyncpg import UniqueViolationError
from docx import Document
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

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
):
    if tier not in ("free", "pro"):
        raise HTTPException(status_code=400, detail="tier must be 'free' or 'pro'")

    suffix = Path(resume.filename or "").suffix.lower()
    if suffix not in (".docx", ".pdf"):
        raise HTTPException(status_code=400, detail="Resume must be .docx or .pdf")

    content = await resume.read()

    resume_text = _extract_docx_text(content) if suffix == ".docx" else _extract_pdf_text(content)

    categories_list  = [c.strip() for c in categories.split(",")   if c.strip()]
    work_models_list = [w.strip() for w in work_models.split(",")  if w.strip()]

    preferences = json.dumps({"categories": categories_list, "work_models": work_models_list})
    work_auth   = json.dumps({"needs_sponsorship": needs_sponsorship})

    pool = get_pool()
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO users (email, tier, preferences, resume_text, work_auth, application_settings)
                VALUES ($1, $2, $3::jsonb, $4, $5::jsonb, '{}'::jsonb)
                RETURNING id
                """,
                email, tier, preferences, resume_text, work_auth,
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
