import asyncio
import hashlib
import logging

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
                await log_company_poll(slug, "greenhouse", "http_404", http_status=404)
                return []
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            logger.debug("Greenhouse HTTP %s for %s", status, slug)
            await increment_consecutive_failures(slug, "greenhouse")
            if status == 429:
                outcome = "http_429"
            elif 400 <= status < 500:
                outcome = "http_4xx"
            else:
                outcome = "http_5xx"
            await log_company_poll(
                slug, "greenhouse", outcome,
                http_status=status, error_detail=str(exc),
            )
            return []
        except httpx.TimeoutException as exc:
            logger.debug("Greenhouse timeout for %s: %s", slug, exc)
            await increment_consecutive_failures(slug, "greenhouse")
            await log_company_poll(slug, "greenhouse", "timeout", error_detail=str(exc))
            return []
        except httpx.RequestError as exc:
            logger.debug("Greenhouse request error for %s: %s", slug, exc)
            await increment_consecutive_failures(slug, "greenhouse")
            await log_company_poll(slug, "greenhouse", "connection_error", error_detail=str(exc))
            return []
        except Exception as exc:
            logger.exception("Greenhouse unexpected error for %s", slug)
            await increment_consecutive_failures(slug, "greenhouse")
            await log_company_poll(slug, "greenhouse", "other_exception", error_detail=str(exc))
            return []

        # Skip entirely if this company's response is byte-identical to last
        # poll — most companies' listings don't change between two 10-min
        # cycles, and parsing + diffing the full response anyway was the
        # root cause of a Jul 22 incident (see migration 024). Hash is
        # computed on the raw body, before any JSON parsing.
        payload_hash = hashlib.sha256(resp.content).hexdigest()
        last_hash, _ = await get_company_payload_hash(slug, "greenhouse")
        if payload_hash == last_hash:
            await reset_consecutive_failures(slug, "greenhouse")
            await log_company_poll(
                slug, "greenhouse", "ok_unchanged",
                http_status=resp.status_code,
            )
            return []

        data = resp.json()
        jobs = data.get("jobs", [])
        results = []
        for job in jobs:
            title = job.get("title", "")
            if not title:
                continue
            location_obj = job.get("location", {}) or {}
            description = job.get("content", "")
            yoe_min, yoe_max = extract_years_of_experience(title, description)
            results.append(
                {
                    "job_id": str(job["id"]),
                    "ats": "greenhouse",
                    "company_slug": slug,
                    "title": title,
                    "location": location_obj.get("name", "Unknown"),
                    "apply_url": job.get("absolute_url", ""),
                    "description_html": description,
                    "categories": assign_categories(title, description),
                    "years_of_experience_min": yoe_min,
                    "years_of_experience_max": yoe_max,
                    "raw_ats_metadata": {
                        "metadata": job.get("metadata"),
                        "departments": job.get("departments"),
                    },
                }
            )
        await reset_consecutive_failures(slug, "greenhouse")
        await set_company_payload_hash(slug, "greenhouse", payload_hash)
        await log_company_poll(
            slug, "greenhouse",
            "ok_with_jobs" if results else "ok_zero_jobs",
            http_status=resp.status_code,
            job_count=len(jobs),
            matched_count=len(results),
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
