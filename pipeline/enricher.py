import logging
import re

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def _slug_to_name(slug: str) -> str:
    return slug.replace("-", " ").title()


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator="\n", strip=True)


def enrich(job: dict) -> dict:
    ats = job["ats"]

    # --- Description extraction ---
    if ats in ("greenhouse", "ashby"):
        description = _html_to_text(job.get("description_html", ""))
    elif ats == "jobright":
        # Jobright has no full JD — use qualifications as the description
        description = job.get("qualifications", "")
    elif ats in ("lever", "smartrecruiters"):
        description = job.get("description_plain", "")
    else:
        # jobvite, simplify, custom — try html first, fall back to plain
        html = job.get("description_html", "")
        description = _html_to_text(html) if html else job.get("description_plain", "")

    # Collapse excessive whitespace
    description = re.sub(r"\n{3,}", "\n\n", description).strip()

    # --- Company name ---
    # Prefer explicit company_name if provided, fall back to deriving from slug
    company_name = job.get("company_name") or _slug_to_name(job["company_slug"])

    return {
        # Core fields (all ATS sources)
        "job_id": job["job_id"],
        "ats": job["ats"],
        "company_slug": job["company_slug"],
        "company_name": company_name,
        "title": job["title"],
        "location": job.get("location", "Unknown"),
        "apply_url": job.get("apply_url", ""),
        "description_plain_text": description,
        # Extended fields (Jobright and future sources)
        "categories": job.get("categories", []),
        "experience_level": job.get("experience_level", ""),
        "work_model": job.get("work_model", "Unknown"),
        "h1b_sponsored": job.get("h1b_sponsored", "Not Sure"),
        "posted_at": job.get("posted_at", 0),
    }
