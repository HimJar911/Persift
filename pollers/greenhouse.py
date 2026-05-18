import asyncio
import logging

import httpx

from pollers.filter import is_intern_role, assign_categories

logger = logging.getLogger(__name__)

BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"

# Max concurrent requests — high enough to move fast through thousands of
# companies, low enough to avoid mass 429s from the API.
_CONCURRENCY = 30


async def _poll_company(
    client: httpx.AsyncClient, slug: str, sem: asyncio.Semaphore
) -> list[dict]:
    async with sem:
        url = BASE_URL.format(slug=slug)
        try:
            resp = await client.get(url, timeout=20)
            if resp.status_code == 429:
                logger.warning("Greenhouse rate-limited on %s — backing off 60s", slug)
                await asyncio.sleep(60)
                resp = await client.get(url, timeout=20)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.debug("Greenhouse HTTP %s for %s", exc.response.status_code, slug)
            return []
        except httpx.RequestError as exc:
            logger.debug("Greenhouse request error for %s: %s", slug, exc)
            return []

        data = resp.json()
        jobs = data.get("jobs", [])
        results = []
        for job in jobs:
            title = job.get("title", "")
            if not is_intern_role(title):
                continue
            location_obj = job.get("location", {}) or {}
            results.append(
                {
                    "job_id": str(job["id"]),
                    "ats": "greenhouse",
                    "company_slug": slug,
                    "title": title,
                    "location": location_obj.get("name", "Unknown"),
                    "apply_url": job.get("absolute_url", ""),
                    "description_html": job.get("content", ""),
                    "categories": assign_categories(title, job.get("content", "")),
                }
            )
        return results


async def poll_greenhouse(slugs: list[str]) -> list[dict]:
    """Poll all Greenhouse companies. *slugs* comes from discovery."""
    logger.info("Polling Greenhouse — %d companies", len(slugs))
    sem = asyncio.Semaphore(_CONCURRENCY)
    all_jobs: list[dict] = []

    async with httpx.AsyncClient() as client:
        tasks = [_poll_company(client, slug, sem) for slug in slugs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, list):
                all_jobs.extend(r)

    logger.info("Greenhouse polling done — %d matching jobs found", len(all_jobs))
    return all_jobs
