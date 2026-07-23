import asyncio
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

BASE_URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"

_CONCURRENCY = 20  # Ashby's API is smaller; be a bit gentler


async def _poll_company(
    client: httpx.AsyncClient, slug: str, sem: asyncio.Semaphore
) -> list[dict]:
    async with sem:
        url = BASE_URL.format(slug=slug)
        # Ashby exposes a real HTTP ETag (verified live, Jul 22) — sending it
        # back via If-None-Match lets the server return an empty 304 instead
        # of the full job list when nothing changed, skipping the download
        # itself (stronger than the hash-after-download approach the other
        # 3 ATSes use, which still pays the transfer cost). See migration
        # 024 / greenhouse.py for why this exists.
        _, last_etag = await get_company_payload_hash(slug, "ashby")
        headers = {"If-None-Match": last_etag} if last_etag else {}
        try:
            resp = await client.get(url, headers=headers, timeout=20)
            if resp.status_code == 429:
                logger.warning("Ashby rate-limited on %s — backing off 60s", slug)
                await asyncio.sleep(60)
                resp = await client.get(url, headers=headers, timeout=20)
            if resp.status_code == 304:
                await reset_consecutive_failures(slug, "ashby")
                await log_company_poll(slug, "ashby", "ok_unchanged", http_status=304)
                return []
            if resp.status_code in (404, 400, 403):
                await log_company_poll(slug, "ashby", "http_404", http_status=resp.status_code)
                return []
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            logger.debug("Ashby HTTP %s for %s", status, slug)
            await increment_consecutive_failures(slug, "ashby")
            outcome = "http_429" if status == 429 else ("http_4xx" if 400 <= status < 500 else "http_5xx")
            await log_company_poll(slug, "ashby", outcome, http_status=status, error_detail=str(exc))
            return []
        except httpx.TimeoutException as exc:
            logger.debug("Ashby timeout for %s: %s", slug, exc)
            await increment_consecutive_failures(slug, "ashby")
            await log_company_poll(slug, "ashby", "timeout", error_detail=str(exc))
            return []
        except httpx.RequestError as exc:
            logger.debug("Ashby request error for %s: %s", slug, exc)
            await increment_consecutive_failures(slug, "ashby")
            await log_company_poll(slug, "ashby", "connection_error", error_detail=str(exc))
            return []

        body = resp.json()
        postings = body.get("jobs") or []

        results = []
        for posting in postings:
            title = posting.get("title", "")
            if not title:
                continue

            location = posting.get("location") or "Unknown"
            if posting.get("isRemote"):
                location = f"{location} (Remote)" if location != "Unknown" else "Remote"

            employment_type = posting.get("employmentType")
            description_html = posting.get("descriptionHtml", "")
            description_plain = posting.get("descriptionPlain", "")
            yoe_min, yoe_max = extract_years_of_experience(
                title, description_plain, description_html
            )

            results.append(
                {
                    "job_id": str(posting["id"]),
                    "ats": "ashby",
                    "company_slug": slug,
                    "title": title,
                    "location": location,
                    "apply_url": posting.get("jobUrl") or posting.get("applyUrl", ""),
                    "description_html": description_html,
                    "description_plain": description_plain,
                    "categories": assign_categories(
                        title, description_html or description_plain,
                    ),
                    "years_of_experience_min": yoe_min,
                    "years_of_experience_max": yoe_max,
                    "raw_ats_metadata": {
                        "department": posting.get("department"),
                        "team": posting.get("team"),
                        "employmentType": employment_type,
                        "workplaceType": posting.get("workplaceType"),
                    },
                }
            )
        await reset_consecutive_failures(slug, "ashby")
        new_etag = resp.headers.get("etag")
        if new_etag:
            await set_company_payload_hash(slug, "ashby", None, etag=new_etag)
        await log_company_poll(
            slug, "ashby",
            "ok_with_jobs" if results else "ok_zero_jobs",
            http_status=resp.status_code,
            job_count=len(postings),
            matched_count=len(results),
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
