"""Workday ATS poller.

Queries Workday's internal JSON API (POST /wday/cxs/{slug}/{board}/jobs)
for each company.  Each company entry carries its own wd_num and board
so the correct endpoint is built per-company.
"""

import asyncio
import logging
import random

import httpx

import config
from pollers.filter import is_intern_role

logger = logging.getLogger(__name__)

_CONCURRENCY = 10
_SEARCH_TEXT = config.WORKDAY_SEARCH_TEXT
_PAGE_LIMIT = 20


async def _poll_company(
    client: httpx.AsyncClient,
    entry: dict,
    sem: asyncio.Semaphore,
) -> list[dict]:
    """Poll a single Workday company/board combo."""
    slug = entry["slug"]
    board = entry["board"]
    base_url = entry["base_url"]
    company_name = entry.get("company_name", slug)
    api_url = f"{base_url}/wday/cxs/{slug}/{board}/jobs"

    all_results: list[dict] = []
    offset = 0

    async with sem:
        # Small random delay for politeness
        await asyncio.sleep(random.uniform(0.1, 0.3))

        while True:
            body = {
                "appliedFacets": {},
                "limit": _PAGE_LIMIT,
                "offset": offset,
                "searchText": _SEARCH_TEXT,
            }
            try:
                resp = await client.post(api_url, json=body, timeout=20)

                if resp.status_code == 429:
                    logger.warning("Workday rate-limited on %s — backing off 30s", slug)
                    await asyncio.sleep(30)
                    resp = await client.post(api_url, json=body, timeout=20)

                if resp.status_code == 404:
                    return []
                resp.raise_for_status()

            except httpx.HTTPStatusError as exc:
                logger.debug("Workday HTTP %s for %s/%s", exc.response.status_code, slug, board)
                return all_results
            except httpx.RequestError as exc:
                logger.debug("Workday request error for %s/%s: %s", slug, board, exc)
                return all_results

            try:
                data = resp.json()
            except Exception:
                logger.debug("Workday bad JSON for %s/%s", slug, board)
                return all_results

            postings = data.get("jobPostings")
            total = data.get("total", 0)
            if postings is None:
                logger.debug("Workday unexpected response for %s/%s", slug, board)
                return all_results

            for job in postings:
                title = job.get("title", "")
                if not is_intern_role(title):
                    continue
                ext_path = job.get("externalPath", "")
                all_results.append(
                    {
                        "job_id": ext_path,
                        "ats": "workday",
                        "company_slug": slug,
                        "company_name": company_name,
                        "title": title,
                        "location": job.get("locationsText", "Unknown"),
                        "apply_url": f"{base_url}{ext_path}" if ext_path else "",
                        "description_plain_text": "",
                    }
                )

            # Paginate if there are more results
            offset += _PAGE_LIMIT
            if offset >= total:
                break

            # Small delay between pages
            await asyncio.sleep(random.uniform(0.1, 0.3))

    return all_results


async def poll_workday(companies: list[dict]) -> list[dict]:
    """Poll all Workday companies. *companies* is a list of entry dicts."""
    logger.info("Polling Workday — %d company/board combos", len(companies))
    sem = asyncio.Semaphore(_CONCURRENCY)
    all_jobs: list[dict] = []

    async with httpx.AsyncClient() as client:
        tasks = [_poll_company(client, entry, sem) for entry in companies]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, list):
                all_jobs.extend(r)

    logger.info("Workday polling done — %d matching jobs found", len(all_jobs))
    return all_jobs
