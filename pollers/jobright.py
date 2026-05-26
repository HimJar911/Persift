"""Jobright poller.

Polls the Jobright API for all intern and new-grad job categories and returns
new jobs in the standard pipeline dict format.  Runs on a 1-hour schedule.

Apply-URL resolution is intentionally lazy: the returned dicts contain an empty
``apply_url`` string that main.py resolves post-dedup by calling
``resolve_apply_url``.
"""

import asyncio
import logging
import re
from html.parser import HTMLParser

import httpx

from pollers.filter import assign_categories

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Category definitions
# ---------------------------------------------------------------------------

_INTERN_CATEGORIES: list[str] = [
    "swe", "ml_ai", "data_analyst", "data_engineer",
    "product_management", "accounting_and_finance", "marketing",
    "cyber_security", "consulting", "human_resources",
    "legal_and_compliance", "sales", "customer_service_and_support",
    "education_and_training", "health care", "supply_chain",
    "creatives_and_design", "engineering_and_development",
    "business_analyst", "management_and_executive",
    "public_sector_and_government", "arts_and_entertainment",
]

# Map new-grad slugs that differ from their intern equivalents.
_NEWGRAD_SLUG_MAP: dict[str, str] = {
    "swe": "software_engineering",
    "ml_ai": "machine_learning_and_ai",
    "data_analyst": "data_analysis",
    "cyber_security": "cybersecurity",
    "project_manager": "project_management",
}

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LIST_URL = "https://jobright.ai/swan/mini-sites/list"
_INFO_URL = "https://jobright.ai/jobs/info/{job_id}"
_PAGE_SIZE = 50
_POLL_SEMAPHORE = 10    # concurrent category-page fetches
_RESOLVE_SEMAPHORE = 5  # conservative — HTML scraping


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_slug(company_name: str) -> str:
    """Derive a URL-safe slug from a company name."""
    return re.sub(r"[^a-z0-9]+", "-", company_name.lower()).strip("-")


def _normalize_category(slug: str, job_type: str) -> str:
    """Return the canonical unified category name for a slug."""
    if job_type == "newgrad":
        return _NEWGRAD_SLUG_MAP.get(slug, slug)
    return slug


class _AnchorParser(HTMLParser):
    """Minimal HTML parser that finds the 'Original Job Post' anchor href."""

    def __init__(self) -> None:
        super().__init__()
        self.href: str = ""
        self._pending_href: str = ""
        self._in_anchor: bool = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._pending_href = dict(attrs).get("href") or ""
            self._in_anchor = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._in_anchor = False
            self._pending_href = ""

    def handle_data(self, data: str) -> None:
        if self._in_anchor and not self.href and "Original Job Post" in data:
            self.href = self._pending_href


class _TextExtractor(HTMLParser):
    """Extracts visible text from HTML, skipping script/style blocks."""

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip: bool = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip:
            stripped = data.strip()
            if stripped:
                self._chunks.append(stripped)

    def get_text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self._chunks)).strip()


# ---------------------------------------------------------------------------
# Per-category page fetching
# ---------------------------------------------------------------------------

async def _fetch_category_page(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    job_type: str,
    category_slug: str,
    offset: int,
) -> list[dict]:
    """Fetch one page of results for a category.  Returns raw job dicts."""
    category_str = f"{job_type}:us:{category_slug}"
    async with sem:
        try:
            resp = await client.post(
                _LIST_URL,
                params={"position": offset, "count": _PAGE_SIZE},
                json={"category": category_str},
                timeout=30,
            )
            if resp.status_code == 429:
                logger.warning(
                    "Jobright rate-limited on %s offset=%d — backing off 60s",
                    category_str, offset,
                )
                await asyncio.sleep(60)
                resp = await client.post(
                    _LIST_URL,
                    params={"position": offset, "count": _PAGE_SIZE},
                    json={"category": category_str},
                    timeout=30,
                )
            resp.raise_for_status()
            data = resp.json()
            return data.get("result", {}).get("jobList", [])
        except Exception as exc:
            logger.warning(
                "Jobright fetch failed for %s offset=%d: %s",
                category_str, offset, exc,
            )
            return []


# Each item in the batch: (raw_job_dict, unified_category, experience_level)
_BatchItem = tuple[dict, str, str]


async def _poll_category(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    job_type: str,
    category_slug: str,
    since_ms: int,
) -> list[_BatchItem]:
    """Poll all pages of one category.

    Returns ``(raw_job, unified_category, experience_level)`` tuples for jobs
    newer than *since_ms*.
    """
    unified_cat = _normalize_category(category_slug, job_type)
    experience_level = "intern" if job_type == "intern" else "newgrad"
    results: list[_BatchItem] = []
    offset = 0

    while True:
        page = await _fetch_category_page(client, sem, job_type, category_slug, offset)
        for raw in page:
            if (raw.get("postedAt") or 0) > since_ms:
                results.append((raw, unified_cat, experience_level))
        if len(page) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE

    return results


# ---------------------------------------------------------------------------
# Apply-URL resolution and JD fetching (called externally post-dedup)
# ---------------------------------------------------------------------------

async def fetch_jd(job_id: str, client: httpx.AsyncClient) -> str:
    """Fetch the Jobright job-info page and return plain-text job description.

    *job_id* is the raw Jobright id (without the ``jobright_`` prefix).
    Returns an empty string on any failure.
    """
    url = _INFO_URL.format(job_id=job_id)
    try:
        resp = await client.get(url, timeout=20)
        resp.raise_for_status()
        extractor = _TextExtractor()
        extractor.feed(resp.text)
        return extractor.get_text()
    except Exception as exc:
        logger.debug("fetch_jd failed for %s: %s", job_id, exc)
        return ""


async def resolve_apply_url(job_id: str, client: httpx.AsyncClient) -> str:
    """Fetch the Jobright job-info page and extract the 'Original Job Post' URL.

    *job_id* is the raw Jobright id (without the ``jobright_`` prefix).
    Returns an empty string on any failure.
    """
    url = _INFO_URL.format(job_id=job_id)
    try:
        resp = await client.get(url, timeout=20)
        resp.raise_for_status()
        parser = _AnchorParser()
        parser.feed(resp.text)
        return parser.href
    except Exception as exc:
        logger.debug("resolve_apply_url failed for %s: %s", job_id, exc)
        return ""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def poll_jobright(since_timestamp: int = 0) -> list[dict]:
    """Poll all Jobright intern and new-grad categories.

    Args:
        since_timestamp: Unix timestamp in milliseconds.  Only jobs with
            ``postedAt > since_timestamp`` are returned.  Pass 0 on first run
            to retrieve everything.

    Returns:
        List of job dicts in the standard pipeline format.  ``apply_url`` is
        always an empty string — resolve it lazily via ``resolve_apply_url``.
    """
    logger.info(
        "Polling Jobright — %d intern categories (newgrad suspended for MVP, since_ms=%d)",
        len(_INTERN_CATEGORIES), since_timestamp,
    )

    sem = asyncio.Semaphore(_POLL_SEMAPHORE)

    async with httpx.AsyncClient() as client:
        # MVP: intern-only. Newgrad re-enabled in v2 with proper role filter.
        coros = [
            _poll_category(client, sem, "intern", cat, since_timestamp)
            for cat in _INTERN_CATEGORIES
        ]
        raw_results = await asyncio.gather(*coros, return_exceptions=True)

    # ------------------------------------------------------------------
    # Merge: same jobId can appear in multiple categories.
    # Accumulate categories; first-seen entry wins for all other fields.
    # ------------------------------------------------------------------
    merged: dict[str, dict] = {}  # keyed on raw jobId string

    for batch in raw_results:
        if isinstance(batch, Exception):
            logger.warning("Jobright category task raised: %s", batch)
            continue
        for raw, unified_cat, experience_level in batch:
            job_id_raw = str(raw.get("jobId") or raw.get("id") or "")
            if not job_id_raw:
                continue

            props = raw.get("properties") or {}
            company_name: str = props.get("company") or ""
            title: str = props.get("title") or ""
            location: str = props.get("location") or "Unknown"
            posted_at: int = int(raw.get("postedAt") or 0)

            # Derive categories from the unified taxonomy via title matching.
            # Jobright's own tabCategory uses a different taxonomy so we ignore
            # it and classify consistently with all other pollers.
            categories = assign_categories(title)
            if not categories:
                categories = [unified_cat]

            if job_id_raw in merged:
                for cat in categories:
                    if cat not in merged[job_id_raw]["categories"]:
                        merged[job_id_raw]["categories"].append(cat)
                continue

            merged[job_id_raw] = {
                "job_id": f"jobright_{job_id_raw}",
                "ats": "jobright",
                "company_slug": _normalize_slug(company_name),
                "company_name": company_name,
                "title": title,
                "location": location,
                "apply_url": "",
                "description_html": "",
                "categories": categories,
                "experience_level": experience_level,
                "posted_at": posted_at,
                "work_model": props.get("workModel") or "Unknown",
                "h1b_sponsored": props.get("h1bSponsored") or "Not Sure",
                "qualifications": props.get("qualifications") or "",
            }

    jobs = list(merged.values())
    logger.info(
        "Jobright polling done — %d unique jobs (since_ms=%d)",
        len(jobs), since_timestamp,
    )
    return jobs
