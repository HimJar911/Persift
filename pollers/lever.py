import asyncio
import logging

import httpx

from pollers.filter import is_intern_role, assign_categories

logger = logging.getLogger(__name__)

BASE_URL = "https://api.lever.co/v0/postings/{slug}?mode=json"

_CONCURRENCY = 30


async def _poll_company(
    client: httpx.AsyncClient, slug: str, sem: asyncio.Semaphore
) -> list[dict]:
    async with sem:
        url = BASE_URL.format(slug=slug)
        try:
            resp = await client.get(url, timeout=20)
            if resp.status_code == 429:
                logger.warning("Lever rate-limited on %s — backing off 60s", slug)
                await asyncio.sleep(60)
                resp = await client.get(url, timeout=20)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.debug("Lever HTTP %s for %s", exc.response.status_code, slug)
            return []
        except httpx.RequestError as exc:
            logger.debug("Lever request error for %s: %s", slug, exc)
            return []

        postings = resp.json()
        if not isinstance(postings, list):
            return []

        results = []
        for posting in postings:
            title = posting.get("text", "")
            if not is_intern_role(title):
                continue
            lever_cats = posting.get("categories", {}) or {}
            results.append(
                {
                    "job_id": str(posting["id"]),
                    "ats": "lever",
                    "company_slug": slug,
                    "title": title,
                    "location": lever_cats.get("location", "Unknown"),
                    "apply_url": posting.get("hostedUrl", ""),
                    "description_plain": posting.get("descriptionPlain", ""),
                    "categories": assign_categories(title, posting.get("descriptionPlain", "")),
                }
            )
        return results


async def poll_lever(slugs: list[str]) -> list[dict]:
    """Poll all Lever companies. *slugs* comes from discovery."""
    logger.info("Polling Lever — %d companies", len(slugs))
    sem = asyncio.Semaphore(_CONCURRENCY)
    all_jobs: list[dict] = []

    async with httpx.AsyncClient() as client:
        tasks = [_poll_company(client, slug, sem) for slug in slugs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, list):
                all_jobs.extend(r)

    logger.info("Lever polling done — %d matching jobs found", len(all_jobs))
    return all_jobs
