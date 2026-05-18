"""Generic poller for companies with custom career APIs.

Reads custom_companies.json and polls each company based on its config.
Adding a new company means only adding an entry to the JSON file — no
code changes needed.
"""

import asyncio
import logging
import random
import re

import httpx

from pollers.filter import is_intern_role, assign_categories

logger = logging.getLogger(__name__)

_CONCURRENCY = 5
_USER_AGENT = "InternRadar/1.0 (internship monitor)"


def _resolve_field(obj, path: str):
    """Resolve a dot-notation field path with optional [N] array indexing.

    Examples:
        "jobs"              -> obj["jobs"]
        "data.positions"    -> obj["data"]["positions"]
        "locations[0]"      -> obj["locations"][0]
    """
    for part in path.split("."):
        # Check for array index: field[N]
        m = re.match(r"^(.+?)\[(\d+)\]$", part)
        if m:
            key, idx = m.group(1), int(m.group(2))
            obj = obj.get(key) if isinstance(obj, dict) else None
            if isinstance(obj, list) and idx < len(obj):
                obj = obj[idx]
            else:
                return None
        elif isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


def _build_apply_url(template: str, job: dict, id_value: str) -> str:
    """Build apply URL from template, replacing {id}, {positionUrl}, etc."""
    url = template.replace("{id}", str(id_value))
    # Support any other {field} placeholders from the job object
    for m in re.finditer(r"\{(\w+)\}", url):
        field = m.group(1)
        if field == "id":
            continue
        val = job.get(field)
        if val is not None:
            url = url.replace(m.group(0), str(val))
    return url


async def _poll_company(
    client: httpx.AsyncClient,
    entry: dict,
    sem: asyncio.Semaphore,
) -> list[dict]:
    """Poll a single custom company."""
    company = entry["company"]
    slug = entry["slug"]
    method = entry.get("method", "GET").upper()
    url = entry["url"]
    base_params = dict(entry.get("params", {}))
    pag = entry.get("pagination", {})
    fields = entry["fields"]

    pag_type = pag.get("type", "offset")
    pag_param = pag.get("param", "offset")
    pag_step = pag.get("step", 100)
    total_field = pag.get("total_field")  # None means paginate until short page

    jobs_array_path = fields["jobs_array"]
    id_field = fields["id"]
    title_field = fields["title"]
    location_field = fields["location"]
    url_template = fields["url_template"]

    all_results: list[dict] = []
    offset = 0

    async with sem:
        await asyncio.sleep(random.uniform(0.3, 1.0))

        while True:
            params = dict(base_params)
            params[pag_param] = offset

            try:
                if method == "POST":
                    resp = await client.post(url, json=params, timeout=20)
                else:
                    resp = await client.get(url, params=params, timeout=20)

                if resp.status_code == 429:
                    logger.warning("Custom poller rate-limited on %s — backing off 30s", slug)
                    await asyncio.sleep(30)
                    if method == "POST":
                        resp = await client.post(url, json=params, timeout=20)
                    else:
                        resp = await client.get(url, params=params, timeout=20)

                if resp.status_code == 404:
                    return []
                resp.raise_for_status()

            except httpx.HTTPStatusError as exc:
                logger.debug("Custom poller HTTP %s for %s", exc.response.status_code, slug)
                return all_results
            except httpx.RequestError as exc:
                logger.debug("Custom poller request error for %s: %s", slug, exc)
                return all_results

            try:
                data = resp.json()
            except Exception:
                logger.debug("Custom poller bad JSON for %s", slug)
                return all_results

            jobs = _resolve_field(data, jobs_array_path)
            if not isinstance(jobs, list):
                logger.debug("Custom poller: no jobs array at '%s' for %s", jobs_array_path, slug)
                return all_results

            for job in jobs:
                title = _resolve_field(job, title_field)
                if not title or not is_intern_role(str(title)):
                    continue

                job_id = _resolve_field(job, id_field)
                location = _resolve_field(job, location_field) or "Unknown"
                apply_url = _build_apply_url(url_template, job, str(job_id))

                all_results.append(
                    {
                        "job_id": str(job_id),
                        "ats": "custom",
                        "company_slug": slug,
                        "company_name": company,
                        "title": str(title),
                        "location": str(location),
                        "apply_url": apply_url,
                        "description_html": "",
                        "categories": assign_categories(str(title)),
                    }
                )

            # Decide whether to continue paginating
            if total_field is not None:
                total = _resolve_field(data, total_field)
                if total is None:
                    total = 0
                offset += pag_step
                if offset >= total:
                    break
            else:
                # No total — stop when page returns fewer results than step
                if len(jobs) < pag_step:
                    break
                offset += pag_step

            await asyncio.sleep(random.uniform(0.3, 1.0))

    return all_results


async def poll_custom(companies: list[dict]) -> list[dict]:
    """Poll all custom company APIs. *companies* is the parsed JSON config."""
    logger.info("Polling Custom APIs — %d companies", len(companies))
    sem = asyncio.Semaphore(_CONCURRENCY)
    headers = {"User-Agent": _USER_AGENT}
    all_jobs: list[dict] = []

    async with httpx.AsyncClient(headers=headers) as client:
        tasks = [_poll_company(client, entry, sem) for entry in companies]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, list):
                all_jobs.extend(r)

    logger.info("Custom API polling done — %d matching jobs found", len(all_jobs))
    return all_jobs
