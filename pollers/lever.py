import asyncio
import hashlib
import logging

import httpx
from bs4 import BeautifulSoup

from db import (
    get_company_payload_hash,
    increment_consecutive_failures,
    log_company_poll,
    reset_consecutive_failures,
    set_company_payload_hash,
)
from pollers.filter import assign_categories
from pollers.geography import normalize_lever_country
from pollers.metadata_categories import map_department
from pollers.seniority import extract_years_of_experience

logger = logging.getLogger(__name__)

BASE_URL = "https://api.lever.co/v0/postings/{slug}?mode=json"


def _lists_to_text(lists: list[dict] | None) -> str:
    """Flatten Lever's `lists` array (section heading + HTML content, e.g.
    "Requirements"/"Qualifications") into plain text.

    Lever splits real posting content across descriptionPlain (intro only)
    and this array — confirmed live (Jul 23 2026 audit) that descriptionPlain
    alone carries ~26% of a posting's total available text, and 35.7% of
    sampled postings had an explicit "N years of experience" phrase sitting
    only here, invisible to extract_years_of_experience()/assign_categories()
    before this fix.
    """
    if not lists:
        return ""
    parts = []
    for section in lists:
        heading = section.get("text", "")
        content_html = section.get("content", "")
        content_text = BeautifulSoup(content_html, "html.parser").get_text(separator="\n", strip=True)
        parts.append(f"{heading}\n{content_text}" if heading else content_text)
    return "\n\n".join(parts)

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
                await log_company_poll(slug, "lever", "http_404", http_status=404)
                return []
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            logger.debug("Lever HTTP %s for %s", status, slug)
            await increment_consecutive_failures(slug, "lever")
            outcome = "http_429" if status == 429 else ("http_4xx" if 400 <= status < 500 else "http_5xx")
            await log_company_poll(slug, "lever", outcome, http_status=status, error_detail=str(exc))
            return []
        except httpx.TimeoutException as exc:
            logger.debug("Lever timeout for %s: %s", slug, exc)
            await increment_consecutive_failures(slug, "lever")
            await log_company_poll(slug, "lever", "timeout", error_detail=str(exc))
            return []
        except httpx.RequestError as exc:
            logger.debug("Lever request error for %s: %s", slug, exc)
            await increment_consecutive_failures(slug, "lever")
            await log_company_poll(slug, "lever", "connection_error", error_detail=str(exc))
            return []

        payload_hash = hashlib.sha256(resp.content).hexdigest()
        last_hash, _ = await get_company_payload_hash(slug, "lever")
        if payload_hash == last_hash:
            await reset_consecutive_failures(slug, "lever")
            await log_company_poll(slug, "lever", "ok_unchanged", http_status=resp.status_code)
            return []

        postings = resp.json()
        if not isinstance(postings, list):
            await log_company_poll(slug, "lever", "other_exception", error_detail="response not a list")
            return []

        results = []
        for posting in postings:
            title = posting.get("text", "")
            if not title:
                continue
            lever_cats = posting.get("categories", {}) or {}
            commitment = lever_cats.get("commitment")
            description_plain = posting.get("descriptionPlain", "")
            lists_text = _lists_to_text(posting.get("lists"))
            full_text = f"{description_plain}\n\n{lists_text}" if lists_text else description_plain
            yoe_min, yoe_max = extract_years_of_experience(title, full_text)
            categories = assign_categories(title, full_text)
            mapped_category = map_department(lever_cats.get("department"))
            if mapped_category and mapped_category not in categories:
                categories.append(mapped_category)
            results.append(
                {
                    "job_id": str(posting["id"]),
                    "ats": "lever",
                    "company_slug": slug,
                    "title": title,
                    "location": lever_cats.get("location", "Unknown"),
                    "apply_url": posting.get("hostedUrl", ""),
                    "description_plain": full_text,
                    "categories": categories,
                    "years_of_experience_min": yoe_min,
                    "years_of_experience_max": yoe_max,
                    "raw_ats_metadata": {
                        "commitment": commitment,
                        "department": lever_cats.get("department"),
                        "team": lever_cats.get("team"),
                        "workplaceType": posting.get("workplaceType"),
                        "country": normalize_lever_country(posting.get("country")),
                    },
                }
            )
        await reset_consecutive_failures(slug, "lever")
        await set_company_payload_hash(slug, "lever", payload_hash)
        await log_company_poll(
            slug, "lever",
            "ok_with_jobs" if results else "ok_zero_jobs",
            http_status=resp.status_code,
            job_count=len(postings),
            matched_count=len(results),
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
