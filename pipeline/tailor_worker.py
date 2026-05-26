"""Tailor worker — processes queued user_jobs through Layer 3 and Layer 4.

Layer 3 (inject_keywords): pure Python, runs inline for all tiers.
Layer 4 (rewrite_resume):  OpenAI call, pro tier only, gated by Semaphore(5).

Single public function: run_tailor_cycle()
Intended cadence: every N minutes via APScheduler.

# pip install weasyprint
"""

import asyncio
import html as _html
import json
import logging
from pathlib import Path

from weasyprint import HTML as _WeasyHTML

from db import get_pool
from pipeline.formatter import check_ats_format
from pipeline.injector import inject_keywords
from pipeline.rewriter import rewrite_resume

logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent.parent
RESUMES_DIR = PROJECT_DIR / "outputs" / "resumes"


def _to_html(resume_text: str) -> str:
    return (
        "<!DOCTYPE html><html><head><style>"
        "@page { size: letter; margin: 0.75in; }"
        "body { font-family: Georgia, serif; font-size: 11pt; }"
        "pre { font-family: inherit; font-size: inherit; white-space: pre-wrap; margin: 0; }"
        "</style></head><body>"
        f"<pre>{_html.escape(resume_text)}</pre>"
        "</body></html>"
    )


def _write_pdf(resume_text: str, pdf_path: Path) -> None:
    _WeasyHTML(string=_to_html(resume_text)).write_pdf(str(pdf_path))


_BATCH_SIZE = 50

_FETCH_SQL = """
SELECT
    uj.id              AS row_id,
    uj.user_id,
    uj.job_id,
    uj.job_ats,
    uj.keyword_match_data,
    uj.retry_count,
    u.tier,
    u.resume_text,
    j.description      AS jd_text,
    j.title,
    j.company_name
FROM user_jobs uj
JOIN users u ON uj.user_id = u.id
JOIN jobs  j ON uj.job_id = j.job_id AND uj.job_ats = j.ats
WHERE uj.status = 'queued'
ORDER BY CASE WHEN u.tier = 'pro' THEN 0 ELSE 1 END, uj.created_at ASC
LIMIT $1
"""


async def _process_row(row: dict, sem: asyncio.Semaphore) -> bool:
    """Run Layers 3 + 4 for one queued user_job.

    Returns True if the row was successfully applied, False if it failed.
    All exceptions are caught here — the caller sees only True/False.
    """
    pool    = get_pool()
    row_id  = row["row_id"]
    user_id = str(row["user_id"])
    job_id  = row["job_id"]
    job_ats = row["job_ats"]

    try:
        kmd_raw = row["keyword_match_data"]
        kmd     = json.loads(kmd_raw) if isinstance(kmd_raw, str) else kmd_raw
        missing = kmd.get("missing", [])
        resume  = row["resume_text"]
        jd_text = row["jd_text"] or ""

        # Layer 3 — keyword injection (pure Python, no semaphore needed)
        injected = inject_keywords(resume, missing)

        # Layer 4 — LLM rewrite (pro only, gated by semaphore)
        if row["tier"] == "pro":
            async with sem:
                final = await asyncio.to_thread(rewrite_resume, injected, jd_text, kmd)
        else:
            final = injected

        # Layer 5 — ATS format check (non-blocking; issues logged but never block)
        fmt = check_ats_format(final)
        if not fmt["passed"]:
            logger.warning(
                "ATS format issues — user_jobs.id=%s: %s",
                row_id, "; ".join(fmt["issues"]),
            )

        # Save tailored resume to disk (.txt for auditing, .pdf for the extension)
        out_dir = RESUMES_DIR / user_id
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_id  = job_id.replace("/", "_")
        txt_path = out_dir / f"{safe_id}_{job_ats}_tailored.txt"
        pdf_path = out_dir / f"{safe_id}_{job_ats}_tailored.pdf"
        txt_path.write_text(final, encoding="utf-8")
        await asyncio.to_thread(_write_pdf, final, pdf_path)

        async with pool.acquire() as conn:
            await conn.execute(
                # 'applying' = resume tailored and ready for the Chrome extension to submit.
                # 'applied'  = set by the extension after confirmed submission.
                """
                UPDATE user_jobs
                SET status = 'applying', tailored_resume_path = $1, updated_at = NOW()
                WHERE id = $2
                """,
                str(pdf_path), row_id,
            )

        if fmt["issues"]:
            try:
                async with pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE user_jobs SET ats_format_issues = $1::jsonb WHERE id = $2",
                        json.dumps(fmt["issues"]), row_id,
                    )
            except Exception:
                pass  # column not yet migrated; issues already logged above

        return True

    except Exception as exc:
        logger.error(
            "Tailor failed — user_jobs.id=%s job=%s/%s: %s",
            row_id, job_ats, job_id, exc,
        )
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE user_jobs
                SET status = 'failed', retry_count = retry_count + 1, updated_at = NOW()
                WHERE id = $1
                """,
                row_id,
            )
        return False


async def run_tailor_cycle() -> None:
    logger.info("=== Tailor cycle starting ===")
    pool = get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch(_FETCH_SQL, _BATCH_SIZE)

    if not rows:
        logger.info("Tailor cycle: no queued jobs")
        return

    logger.info("Tailor cycle: processing %d queued jobs (pro first)", len(rows))

    sem     = asyncio.Semaphore(5)
    tasks   = [asyncio.create_task(_process_row(dict(r), sem)) for r in rows]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    applied = sum(1 for r in results if r is True)
    failed  = len(results) - applied
    logger.info(
        "Tailor cycle done — %d applied, %d failed (of %d)",
        applied, failed, len(rows),
    )
