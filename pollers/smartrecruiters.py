"""SmartRecruiters ATS poller.

Queries the public SmartRecruiters API
(GET /v1/companies/{slug}/postings?limit=100&offset=0) for each company.
Paginates via offset until content is empty or offset >= totalFound.

Keeps every job the API returns (migration 022 — no title-keyword drop gate;
see pollers/seniority.py's module docstring for why). This endpoint doesn't
return a description, so years-of-experience extraction only has the title
to scan — real signal when a title states it ("5+ Years Experience"), NULL
otherwise, same as everywhere else.
"""

import asyncio
import hashlib
import logging
import random

import httpx

from db import (
    get_company_payload_hash,
    increment_consecutive_failures,
    log_company_poll,
    reset_consecutive_failures,
    set_company_payload_hash,
)
from pollers.filter import assign_categories
from pollers.seniority import extract_years_of_experience

logger = logging.getLogger(__name__)

_CONCURRENCY = 10
_PAGE_LIMIT = 100
_BASE_URL = "https://api.smartrecruiters.com/v1/companies/{slug}/postings"
_APPLY_URL = "https://jobs.smartrecruiters.com/{slug}/{job_id}"

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
    total = 0
    single_page_hash: str | None = None
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
                    await log_company_poll(slug, "smartrecruiters", "http_404", http_status=404)
                    return []
                resp.raise_for_status()

            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                logger.debug("SmartRecruiters HTTP %s for %s", status, slug)
                await increment_consecutive_failures(slug, "smartrecruiters")
                outcome = "http_429" if status == 429 else ("http_4xx" if 400 <= status < 500 else "http_5xx")
                await log_company_poll(
                    slug, "smartrecruiters", outcome,
                    http_status=status, job_count=offset, matched_count=len(all_results),
                    error_detail=str(exc),
                )
                return all_results
            except httpx.TimeoutException as exc:
                logger.debug("SmartRecruiters timeout for %s: %s", slug, exc)
                await increment_consecutive_failures(slug, "smartrecruiters")
                await log_company_poll(
                    slug, "smartrecruiters", "timeout",
                    job_count=offset, matched_count=len(all_results), error_detail=str(exc),
                )
                return all_results
            except httpx.RequestError as exc:
                logger.debug("SmartRecruiters request error for %s: %s", slug, exc)
                await increment_consecutive_failures(slug, "smartrecruiters")
                await log_company_poll(
                    slug, "smartrecruiters", "connection_error",
                    job_count=offset, matched_count=len(all_results), error_detail=str(exc),
                )
                return all_results

            try:
                data = resp.json()
            except Exception:
                logger.debug("SmartRecruiters bad JSON for %s", slug)
                await increment_consecutive_failures(slug, "smartrecruiters")
                await log_company_poll(
                    slug, "smartrecruiters", "other_exception",
                    job_count=offset, matched_count=len(all_results), error_detail="invalid JSON",
                )
                return all_results

            content = data.get("content")
            total = data.get("totalFound", 0)

            # Single-page companies (the common case — most tracked
            # employers post far fewer than one page's worth of jobs) can be
            # skipped entirely on an unchanged payload, before any parsing.
            # Multi-page companies still get fully fetched+parsed (smaller
            # win there, but correctness over optimizing the rarer big-
            # employer case). See migration 024 / greenhouse.py for why.
            if offset == 0 and total <= _PAGE_LIMIT:
                single_page_hash = hashlib.sha256(resp.content).hexdigest()
                last_hash, _ = await get_company_payload_hash(slug, "smartrecruiters")
                if single_page_hash == last_hash:
                    await reset_consecutive_failures(slug, "smartrecruiters")
                    await log_company_poll(
                        slug, "smartrecruiters", "ok_unchanged",
                        http_status=resp.status_code,
                    )
                    return []

            if content is None:
                logger.debug("SmartRecruiters unexpected response for %s", slug)
                await increment_consecutive_failures(slug, "smartrecruiters")
                await log_company_poll(
                    slug, "smartrecruiters", "other_exception",
                    job_count=offset, matched_count=len(all_results),
                    error_detail="missing 'content' key",
                )
                return all_results

            if not content:
                break

            for job in content:
                title = job.get("name", "")
                if not title:
                    continue
                job_id = str(job.get("id", ""))
                location = job.get("location", {}) or {}
                company = job.get("company", {}) or {}
                experience_level = job.get("experienceLevel")
                yoe_min, yoe_max = extract_years_of_experience(title)
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
                        "years_of_experience_min": yoe_min,
                        "years_of_experience_max": yoe_max,
                        "raw_ats_metadata": {
                            "experienceLevel": experience_level,
                            "function": job.get("function"),
                            "department": job.get("department"),
                            "typeOfEmployment": job.get("typeOfEmployment"),
                            "industry": job.get("industry"),
                        },
                    }
                )

            offset += _PAGE_LIMIT
            if offset >= total:
                break

            await asyncio.sleep(random.uniform(0.1, 0.3))

    await reset_consecutive_failures(slug, "smartrecruiters")
    if single_page_hash is not None:
        await set_company_payload_hash(slug, "smartrecruiters", single_page_hash)
    await log_company_poll(
        slug, "smartrecruiters",
        "ok_with_jobs" if all_results else "ok_zero_jobs",
        job_count=total,
        matched_count=len(all_results),
    )
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
