import asyncio
import hashlib
import logging
import xml.etree.ElementTree as ET

import httpx

from pollers.filter import is_intern_role, assign_categories

logger = logging.getLogger(__name__)

API_URL = "https://jobs.jobvite.com/api/company/{slug}/jobfeed"

_CONCURRENCY = 10


def _parse_xml_jobs(xml_text: str, slug: str) -> list[dict]:
    """Parse Jobvite XML job feed and return matching jobs."""
    results = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return results

    # Jobvite XML can use various structures — search for job elements
    for job in root.iter():
        title_el = job.find("title")
        if title_el is None or not title_el.text:
            continue
        title = title_el.text.strip()
        if not is_intern_role(title):
            continue

        apply_el = job.find("apply-url") or job.find("apply_url") or job.find("url")
        location_el = job.find("location")
        id_el = job.find("id") or job.find("requisitionid")

        job_id = id_el.text.strip() if id_el is not None and id_el.text else ""
        if not job_id:
            # Use a stable deterministic hash as fallback ID
            job_id = hashlib.md5(f"{slug}:{title}".encode()).hexdigest()

        results.append(
            {
                "job_id": job_id,
                "ats": "jobvite",
                "company_slug": slug,
                "title": title,
                "location": location_el.text.strip() if location_el is not None and location_el.text else "Unknown",
                "apply_url": apply_el.text.strip() if apply_el is not None and apply_el.text else "",
                "description_plain": "",
                "categories": assign_categories(title),
            }
        )
    return results


async def _poll_company(
    client: httpx.AsyncClient, slug: str, sem: asyncio.Semaphore
) -> list[dict]:
    async with sem:
        url = API_URL.format(slug=slug)
        try:
            resp = await client.get(url, timeout=20)
            if resp.status_code == 429:
                logger.warning("Jobvite rate-limited on %s — backing off 60s", slug)
                await asyncio.sleep(60)
                resp = await client.get(url, timeout=20)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.debug("Jobvite HTTP %s for %s", exc.response.status_code, slug)
            return []
        except httpx.RequestError as exc:
            logger.debug("Jobvite request error for %s: %s", slug, exc)
            return []

        return _parse_xml_jobs(resp.text, slug)


async def poll_jobvite(slugs: list[str]) -> list[dict]:
    """Poll all Jobvite companies. *slugs* comes from discovery."""
    logger.info("Polling Jobvite — %d companies", len(slugs))
    sem = asyncio.Semaphore(_CONCURRENCY)
    all_jobs: list[dict] = []

    async with httpx.AsyncClient() as client:
        tasks = [_poll_company(client, slug, sem) for slug in slugs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, list):
                all_jobs.extend(r)

    logger.info("Jobvite polling done — %d matching jobs found", len(all_jobs))
    return all_jobs
