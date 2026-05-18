import asyncio
import logging

import httpx

from pollers.filter import is_intern_role, assign_categories

logger = logging.getLogger(__name__)

BASE_URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"

_CONCURRENCY = 20  # Ashby's API is smaller; be a bit gentler


async def _poll_company(
    client: httpx.AsyncClient, slug: str, sem: asyncio.Semaphore
) -> list[dict]:
    async with sem:
        url = BASE_URL.format(slug=slug)
        try:
            resp = await client.get(url, timeout=20)
            if resp.status_code == 429:
                logger.warning("Ashby rate-limited on %s — backing off 60s", slug)
                await asyncio.sleep(60)
                resp = await client.get(url, timeout=20)
            if resp.status_code in (404, 400, 403):
                return []
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.debug("Ashby HTTP %s for %s", exc.response.status_code, slug)
            return []
        except httpx.RequestError as exc:
            logger.debug("Ashby request error for %s: %s", slug, exc)
            return []

        body = resp.json()
        postings = body.get("jobs") or []

        results = []
        for posting in postings:
            title = posting.get("title", "")
            if not is_intern_role(title):
                continue

            location = posting.get("location") or "Unknown"
            if posting.get("isRemote"):
                location = f"{location} (Remote)" if location != "Unknown" else "Remote"

            results.append(
                {
                    "job_id": str(posting["id"]),
                    "ats": "ashby",
                    "company_slug": slug,
                    "title": title,
                    "location": location,
                    "apply_url": posting.get("jobUrl") or posting.get("applyUrl", ""),
                    "description_html": posting.get("descriptionHtml", ""),
                    "description_plain": posting.get("descriptionPlain", ""),
                    "categories": assign_categories(
                        title,
                        posting.get("descriptionHtml", "") or posting.get("descriptionPlain", ""),
                    ),
                }
            )
        return results


async def poll_ashby(slugs: list[str]) -> list[dict]:
    """Poll all Ashby companies. *slugs* comes from discovery."""
    logger.info("Polling Ashby — %d companies", len(slugs))
    sem = asyncio.Semaphore(_CONCURRENCY)
    all_jobs: list[dict] = []

    async with httpx.AsyncClient() as client:
        tasks = [_poll_company(client, slug, sem) for slug in slugs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, list):
                all_jobs.extend(r)

    logger.info("Ashby polling done — %d matching jobs found", len(all_jobs))
    return all_jobs
