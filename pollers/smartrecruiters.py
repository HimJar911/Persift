"""SmartRecruiters ATS poller.

Queries the public SmartRecruiters API
(GET /v1/companies/{slug}/postings?limit=100&offset=0) for each company.
Paginates via offset until content is empty or offset >= totalFound.
"""

import asyncio
import logging
import random

import httpx

from db import increment_consecutive_failures, reset_consecutive_failures
from pollers.filter import is_intern_role, assign_categories

logger = logging.getLogger(__name__)

_CONCURRENCY = 10
_PAGE_LIMIT = 100
_BASE_URL = "https://api.smartrecruiters.com/v1/companies/{slug}/postings"
_APPLY_URL = "https://jobs.smartrecruiters.com/{slug}/{job_id}"

MAX_PAGES = 3

BLACKLISTED_SLUGS = frozenset([
    "jobsforhumanity", "westgateresorts", "veolia", "prosidianconsulting", "usm",
    "redbull",
])


async def _poll_company(
    client: httpx.AsyncClient,
    slug: str,
    sem: asyncio.Semaphore,
) -> list[dict]:
    """Poll a single SmartRecruiters company."""
    if slug in BLACKLISTED_SLUGS:
        return []

    all_results: list[dict] = []
    offset = 0
    page = 0
    url = _BASE_URL.format(slug=slug)

    async with sem:
        await asyncio.sleep(random.uniform(0.1, 0.3))

        while True:
            params = {"limit": _PAGE_LIMIT, "offset": offset}
            try:
                resp = await client.get(url, params=params, timeout=20)

                if resp.status_code == 429:
                    logger.warning("SmartRecruiters rate-limited on %s — backing off 30s", slug)
                    await asyncio.sleep(30)
                    resp = await client.get(url, params=params, timeout=20)

                if resp.status_code == 404:
                    return []
                resp.raise_for_status()

            except httpx.HTTPStatusError as exc:
                logger.debug("SmartRecruiters HTTP %s for %s", exc.response.status_code, slug)
                await increment_consecutive_failures(slug, "smartrecruiters")
                return all_results
            except httpx.RequestError as exc:
                logger.debug("SmartRecruiters request error for %s: %s", slug, exc)
                await increment_consecutive_failures(slug, "smartrecruiters")
                return all_results

            try:
                data = resp.json()
            except Exception:
                logger.debug("SmartRecruiters bad JSON for %s", slug)
                await increment_consecutive_failures(slug, "smartrecruiters")
                return all_results

            content = data.get("content")
            total = data.get("totalFound", 0)
            if content is None:
                logger.debug("SmartRecruiters unexpected response for %s", slug)
                await increment_consecutive_failures(slug, "smartrecruiters")
                return all_results

            if not content:
                break

            page_matches = 0
            for job in content:
                title = job.get("name", "")
                if not is_intern_role(title):
                    continue
                page_matches += 1
                job_id = str(job.get("id", ""))
                location = job.get("location", {}) or {}
                company = job.get("company", {}) or {}
                all_results.append(
                    {
                        "job_id": job_id,
                        "ats": "smartrecruiters",
                        "company_slug": slug,
                        "company_name": company.get("name", slug),
                        "title": title,
                        "location": location.get("fullLocation", "Unknown"),
                        "apply_url": _APPLY_URL.format(slug=slug, job_id=job_id),
                        "description_html": "",
                        "categories": assign_categories(title),
                    }
                )

            # Early exit: first page had no intern matches — not worth paginating
            if page == 0 and page_matches == 0:
                break

            page += 1
            offset += _PAGE_LIMIT
            if offset >= total or page >= MAX_PAGES:
                break

            await asyncio.sleep(random.uniform(0.1, 0.3))

    await reset_consecutive_failures(slug, "smartrecruiters")
    return all_results


async def poll_smartrecruiters(slugs: list[str]) -> list[dict]:
    """Poll all SmartRecruiters companies. *slugs* is a list of company identifiers."""
    logger.info("Polling SmartRecruiters — %d companies", len(slugs))
    sem = asyncio.Semaphore(_CONCURRENCY)
    all_jobs: list[dict] = []

    async with httpx.AsyncClient() as client:
        tasks = [_poll_company(client, slug, sem) for slug in slugs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, list):
                all_jobs.extend(r)

    logger.info("SmartRecruiters polling done — %d matching jobs found", len(all_jobs))
    return all_jobs
