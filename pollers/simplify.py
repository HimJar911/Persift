"""Simplify catch-all poller.

Fetches the SimplifyJobs listings JSON from GitHub and surfaces internships
from companies whose ATS platforms we don't already poll directly (Apple,
Google, Meta, Cisco, iCIMS companies, Oracle Cloud, etc.).

This runs on a separate 1-hour schedule, not the 10-minute Tier 1 cycle.
"""

import json
import logging
import re
from pathlib import Path

import httpx

import config
from pollers.filter import matches_title

logger = logging.getLogger(__name__)

_RAW_URL = config.SIMPLIFY_LISTINGS_URL

# ATS domains we already poll via dedicated pollers — skip these URLs.
_KNOWN_ATS_DOMAINS = re.compile(
    r"(?:greenhouse\.io|lever\.co|ashbyhq\.com|jobvite\.com"
    r"|myworkdayjobs\.com|smartrecruiters\.com)",
    re.IGNORECASE,
)

_REQUEST_TIMEOUT = 60  # large JSON file


def _load_custom_slugs() -> frozenset[str]:
    """Load company slugs from custom_companies.json to exclude them."""
    path = Path(__file__).resolve().parent.parent / "custom_companies.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return frozenset(
            entry["slug"].lower() for entry in data if isinstance(entry, dict)
        )
    except (OSError, json.JSONDecodeError, KeyError):
        return frozenset()


def _normalize_slug(company_name: str) -> str:
    """Derive a URL-safe slug from a company name."""
    return re.sub(r"[^a-z0-9]+", "-", company_name.lower()).strip("-")


async def fetch_simplify_listings() -> list[dict]:
    """Fetch listings from GitHub raw URL."""
    logger.info("Fetching Simplify listings from GitHub...")
    async with httpx.AsyncClient() as client:
        resp = await client.get(_RAW_URL, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        listings = resp.json()
    logger.info("Fetched %d total Simplify listings", len(listings))
    return listings


async def poll_simplify() -> list[dict]:
    """Fetch Simplify listings and return jobs not covered by other pollers."""
    try:
        listings = await fetch_simplify_listings()
    except Exception:
        logger.exception("Failed to fetch Simplify listings")
        return []

    custom_slugs = _load_custom_slugs()
    results: list[dict] = []

    for item in listings:
        # Skip inactive listings
        if not item.get("active", False):
            continue

        url = item.get("url", "") or ""

        # Skip listings on ATS platforms we already poll
        if _KNOWN_ATS_DOMAINS.search(url):
            continue

        # Skip companies handled by the custom poller
        company_name = item.get("company_name", "")
        if _normalize_slug(company_name) in custom_slugs:
            continue

        title = item.get("title", "")
        if not matches_title(title):
            continue

        listing_id = item.get("id", "")
        if not listing_id:
            continue

        locations = item.get("locations", [])
        location = locations[0] if locations else "Unknown"

        results.append(
            {
                "job_id": str(listing_id),
                "ats": "simplify",
                "company_slug": _normalize_slug(company_name),
                "company_name": company_name,
                "title": title,
                "location": location,
                "apply_url": url,
                "description_html": "",
            }
        )

    logger.info(
        "Simplify polling done — %d matching jobs (after excluding known ATS domains)",
        len(results),
    )
    return results
