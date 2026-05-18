"""Discover companies on Greenhouse, Lever, and Ashby via Common Crawl CDX API.

Queries the Common Crawl index for every URL matching each ATS platform's
job-board domain, extracts company slugs from the URL paths, deduplicates,
and saves the results as JSON files that the main polling system reads.

The script automatically discovers the latest Common Crawl index, paginates
through all results (one CDX block per page to stay under the server's
timeout threshold), and adds polite delays between requests.

Usage:
    python discover_companies.py                           # auto-detect latest crawl
    python discover_companies.py --crawl CC-MAIN-2026-12   # specify index
"""

import argparse
import asyncio
import json
import logging
import re
import sys
import time
from pathlib import Path

import httpx

from config import (
    GREENHOUSE_FALLBACK_SLUGS, LEVER_FALLBACK_SLUGS, ASHBY_FALLBACK_SLUGS,
    SMARTRECRUITERS_FALLBACK_SLUGS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("discover-companies")

PROJECT_DIR = Path(__file__).resolve().parent

COLLINFO_URL = "https://index.commoncrawl.org/collinfo.json"

# The CDX server is a shared free resource — keep requests small and polite.
# pageSize=1 means one CDX block per HTTP response which stays well under
# the server's internal timeout.  Each block typically holds 500-3000 records.
_PAGE_SIZE = 1
_REQUEST_TIMEOUT = 120  # seconds — CDX data pages can be slow
_PAGE_DELAY = 1         # seconds between page fetches (politeness)
_RETRY_LIMIT = 3
_RETRY_DELAY = 5        # seconds between retries on failure

# Lever-specific overrides — its CDX pages are much larger and slower
_LEVER_TIMEOUT = 180
_LEVER_RETRY_LIMIT = 5
_LEVER_PAGE_DELAY = 3

# False-positive slugs that appear in URLs but are not real companies
_SKIP_SLUGS = frozenset({
    "favicon.ico", "robots.txt", "sitemap.xml",
    "api", "v1", "v2", "static", "assets", "cdn",
})

ATS_PLATFORMS = {
    "greenhouse": {
        "domain": "boards.greenhouse.io",
        "output": PROJECT_DIR / "greenhouse_companies.json",
        "slug_regex": re.compile(r"^https?://boards\.greenhouse\.io/([^/?#]+)"),
        "fallback": GREENHOUSE_FALLBACK_SLUGS,
    },
    "lever": {
        "domain": "jobs.lever.co",
        "output": PROJECT_DIR / "lever_companies.json",
        "slug_regex": re.compile(r"^https?://jobs\.lever\.co/([^/?#]+)"),
        "fallback": LEVER_FALLBACK_SLUGS,
        "timeout": _LEVER_TIMEOUT,
        "retry_limit": _LEVER_RETRY_LIMIT,
        "page_delay": _LEVER_PAGE_DELAY,
        "merge_existing": True,
    },
    "ashby": {
        "domain": "jobs.ashbyhq.com",
        "output": PROJECT_DIR / "ashby_companies.json",
        "slug_regex": re.compile(r"^https?://jobs\.ashbyhq\.com/([^/?#]+)"),
        "fallback": ASHBY_FALLBACK_SLUGS,
    },
    "smartrecruiters": {
        "domain": "jobs.smartrecruiters.com",
        "output": PROJECT_DIR / "smartrecruiters_companies.json",
        "slug_regex": re.compile(r"^https?://jobs\.smartrecruiters\.com/([^/?#]+)"),
        "fallback": SMARTRECRUITERS_FALLBACK_SLUGS,
    },
}


# ---------------------------------------------------------------------------
# Step 1: Discover latest crawl index
# ---------------------------------------------------------------------------

_PROBE_DOMAIN = "boards.greenhouse.io"
_PROBE_TIMEOUT = 20   # short — just a liveness check, fail fast
_MAX_PROBE_ATTEMPTS = 3


def get_latest_cdx_api(client: httpx.Client, crawl_override: str | None) -> tuple[str, str]:
    """Return (crawl_id, cdx_api_url) for the latest *ready* Common Crawl index.

    If crawl_override is given, find that specific crawl in the list (no fallback).
    Otherwise, probe crawls newest-first until one answers a page-count query —
    skipping any that are still being indexed (timeouts / errors).  Tries up to
    _MAX_PROBE_ATTEMPTS crawls before raising RuntimeError.
    """
    logger.info("Fetching Common Crawl index list from %s", COLLINFO_URL)
    resp = client.get(COLLINFO_URL, timeout=30)
    resp.raise_for_status()
    crawls = resp.json()

    if not crawls:
        raise RuntimeError("Common Crawl collinfo.json returned empty list")

    # Sort by id descending to get the latest first
    crawls.sort(key=lambda c: c["id"], reverse=True)

    if crawl_override:
        for c in crawls:
            if c["id"] == crawl_override:
                logger.info("Using specified crawl: %s", c["id"])
                return c["id"], c["cdx-api"]
        raise RuntimeError(
            f"Crawl {crawl_override!r} not found. "
            f"Latest available: {crawls[0]['id']}"
        )

    # Auto-select: probe up to _MAX_PROBE_ATTEMPTS crawls, newest first.
    for c in crawls[:_MAX_PROBE_ATTEMPTS]:
        crawl_id = c["id"]
        cdx_api = c["cdx-api"]
        logger.info("Probing crawl %s...", crawl_id)
        pages = _get_num_pages(
            client, cdx_api, _PROBE_DOMAIN, "probe",
            timeout=_PROBE_TIMEOUT, retry_limit=1,
        )
        if pages is not None:
            logger.info("Using crawl %s (%d pages for probe domain)", crawl_id, pages)
            return crawl_id, cdx_api
        logger.warning("Crawl %s not ready — trying previous", crawl_id)

    tried = [c["id"] for c in crawls[:_MAX_PROBE_ATTEMPTS]]
    raise RuntimeError(
        f"No ready Common Crawl index found after probing {_MAX_PROBE_ATTEMPTS} crawls. "
        f"Tried: {tried}"
    )


# ---------------------------------------------------------------------------
# Step 2 & 3: Query CDX with pagination and extract slugs
# ---------------------------------------------------------------------------

def _is_valid_slug(slug: str) -> bool:
    """Filter out noise: too short, too long, contains dots/slashes/spaces."""
    if len(slug) < 2 or len(slug) > 80:
        return False
    if "." in slug or "/" in slug or " " in slug:
        return False
    if slug in _SKIP_SLUGS:
        return False
    return True


def _fetch_with_retry(
    client: httpx.Client,
    url: str,
    label: str,
    timeout: int = _REQUEST_TIMEOUT,
    retry_limit: int = _RETRY_LIMIT,
) -> httpx.Response | None:
    """Fetch a URL with retry logic. Returns Response or None on total failure."""
    for attempt in range(retry_limit):
        try:
            resp = client.get(url, timeout=timeout)
            # Detect HTML error pages returned with 200 status
            if resp.status_code == 200 and resp.text.strip().startswith("<"):
                raise httpx.HTTPStatusError(
                    "CDX returned HTML error page",
                    request=resp.request,
                    response=resp,
                )
            resp.raise_for_status()
            return resp
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            logger.warning(
                "%s: request failed (%s), attempt %d/%d",
                label, exc, attempt + 1, retry_limit,
            )
            if attempt < retry_limit - 1:
                time.sleep(_RETRY_DELAY)
    return None


def _get_num_pages(
    client: httpx.Client,
    cdx_api: str,
    domain: str,
    label: str,
    timeout: int = _REQUEST_TIMEOUT,
    retry_limit: int = _RETRY_LIMIT,
) -> int | None:
    """Ask the CDX API how many pages are available for this domain."""
    url = (
        f"{cdx_api}?url={domain}&matchType=domain"
        f"&output=json&fl=url&showNumPages=true&pageSize={_PAGE_SIZE}"
    )
    resp = _fetch_with_retry(client, url, label, timeout=timeout, retry_limit=retry_limit)
    if resp is None:
        return None

    text = resp.text.strip()

    # Response is JSON: {"pages": N, "pageSize": M, "blocks": B}
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "pages" in data:
            return int(data["pages"])
        if isinstance(data, int):
            return data
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: plain integer
    try:
        return int(text)
    except ValueError:
        logger.warning("%s: unexpected numPages response: %r", label, text[:200])
        return None


def _fetch_page_slugs(
    client: httpx.Client,
    cdx_api: str,
    domain: str,
    regex: re.Pattern,
    page: int,
    label: str,
    timeout: int = _REQUEST_TIMEOUT,
    retry_limit: int = _RETRY_LIMIT,
    slug_filter=None,
) -> list[str]:
    """Fetch one page of CDX results and extract slugs."""
    url = (
        f"{cdx_api}?url={domain}&matchType=domain"
        f"&output=json&fl=url&pageSize={_PAGE_SIZE}&page={page}"
    )
    resp = _fetch_with_retry(client, url, label, timeout=timeout, retry_limit=retry_limit)
    if resp is None:
        return []

    slugs: list[str] = []
    for line in resp.text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        raw_url = record.get("url", "")
        m = regex.match(raw_url)
        if m:
            slug = m.group(1).lower().strip()
            if _is_valid_slug(slug):
                if slug_filter is None or slug_filter(slug):
                    slugs.append(slug)

    return slugs


def discover_ats(
    client: httpx.Client,
    ats_name: str,
    cdx_api: str,
) -> tuple[list[str] | None, int]:
    """Discover all company slugs for one ATS platform via paginated CDX queries.

    Returns (sorted deduplicated list of slugs or None, pages_fetched).
    None means the CDX API was completely unreachable.
    """
    cfg = ATS_PLATFORMS[ats_name]
    domain = cfg["domain"]
    regex = cfg["slug_regex"]
    label = ats_name.title()
    slug_filter = cfg.get("slug_filter")

    # Per-platform overrides
    timeout = cfg.get("timeout", _REQUEST_TIMEOUT)
    retry_limit = cfg.get("retry_limit", _RETRY_LIMIT)
    page_delay = cfg.get("page_delay", _PAGE_DELAY)

    # Get total page count
    logger.info("%s: checking page count...", label)
    num_pages = _get_num_pages(
        client, cdx_api, domain, label,
        timeout=timeout, retry_limit=retry_limit,
    )
    if num_pages is None:
        logger.error("%s: could not determine page count — skipping", label)
        return None, 0
    if num_pages == 0:
        logger.warning("%s: CDX returned 0 pages", label)
        return [], 0

    logger.info("%s: %d pages to fetch", label, num_pages)

    # Fetch all pages with progress and politeness delay
    all_slugs: list[str] = []
    pages_ok = 0
    for page in range(num_pages):
        print(f"  {label}: fetching page {page + 1}/{num_pages}...", flush=True)
        page_slugs = _fetch_page_slugs(
            client, cdx_api, domain, regex, page, label,
            timeout=timeout, retry_limit=retry_limit,
            slug_filter=slug_filter,
        )
        all_slugs.extend(page_slugs)
        if page_slugs:
            pages_ok += 1

        # Politeness delay between pages (skip after last page)
        if page < num_pages - 1:
            time.sleep(page_delay)

    # Deduplicate and sort
    unique = sorted(set(all_slugs))
    logger.info(
        "%s: %d/%d pages fetched, %d unique slugs (from %d raw matches)",
        label, pages_ok, num_pages, len(unique), len(all_slugs),
    )

    # Merge with existing file if configured (e.g. Lever — CDX is unreliable)
    if cfg.get("merge_existing"):
        existing = _load_existing(cfg["output"])
        if existing:
            cdx_count = len(unique)
            merged = sorted(set(unique) | set(existing))
            logger.info(
                "%s: merged %d CDX slugs with %d existing → %d total",
                label, cdx_count, len(existing), len(merged),
            )
            unique = merged

    return unique, num_pages


# ---------------------------------------------------------------------------
# Slug validation — ping live ATS APIs to confirm slugs are active
# ---------------------------------------------------------------------------

_ATS_VALIDATION_URLS: dict[str, str] = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "smartrecruiters": "https://api.smartrecruiters.com/v1/companies/{slug}/postings",
}

_VALIDATION_CONCURRENCY = 50
_VALIDATION_TIMEOUT = 10


async def _validate_slug(
    session: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    ats_name: str,
    slug: str,
) -> str | None:
    """Return slug if live, None if dead (404/400) or error."""
    url = _ATS_VALIDATION_URLS[ats_name].format(slug=slug)
    async with sem:
        try:
            resp = await session.get(url, timeout=_VALIDATION_TIMEOUT)
            if resp.status_code in (200, 403):
                # 403 means the company exists but restricted — still valid
                return slug
            return None
        except Exception:
            return None


async def validate_slugs(ats_name: str, slugs: list[str]) -> list[str]:
    """Validate slugs against live ATS API. Returns only active slugs."""
    if ats_name not in _ATS_VALIDATION_URLS:
        logger.info("%s: no validation URL configured — skipping validation", ats_name.title())
        return slugs

    logger.info("%s: validating %d slugs...", ats_name.title(), len(slugs))
    sem = asyncio.Semaphore(_VALIDATION_CONCURRENCY)

    async with httpx.AsyncClient() as session:
        tasks = [
            _validate_slug(session, sem, ats_name, slug)
            for slug in slugs
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    valid = [
        slug for slug, result in zip(slugs, results)
        if result and not isinstance(result, Exception)
    ]
    logger.info(
        "%s: %d/%d slugs validated as active",
        ats_name.title(), len(valid), len(slugs),
    )
    return valid


# ---------------------------------------------------------------------------
# Step 5 & 6: Save, fallback, and summary
# ---------------------------------------------------------------------------

def _load_existing(path: Path) -> list[str]:
    """Load an existing JSON company list, or return empty list."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return []


def run_discovery(crawl_override: str | None = None) -> None:
    """Discover companies for all ATS platforms and save results."""
    client = httpx.Client()

    try:
        crawl_id, cdx_api = get_latest_cdx_api(client, crawl_override)
    except Exception as exc:
        logger.error("Failed to get Common Crawl index info: %s", exc)
        logger.warning("Keeping existing company files unchanged")
        client.close()
        return

    names = list(ATS_PLATFORMS.keys())
    results: dict[str, list[str]] = {}
    page_counts: dict[str, int] = {}

    # Run sequentially — polite to Common Crawl servers
    for name in names:
        slugs, num_pages = discover_ats(client, name, cdx_api)
        cfg = ATS_PLATFORMS[name]
        page_counts[name] = num_pages

        if slugs is None or (len(slugs) == 0 and num_pages > 0):
            # CDX unreachable or returned empty despite having pages — keep existing
            existing = _load_existing(cfg["output"])
            if existing:
                reason = "unreachable" if slugs is None else "returned 0 slugs"
                logger.warning(
                    "%s: CDX %s — keeping existing file (%d companies)",
                    name.title(), reason, len(existing),
                )
                results[name] = existing
            else:
                fallback = list(cfg["fallback"])
                logger.warning(
                    "%s: CDX failed and no existing file — using hardcoded fallback (%d companies)",
                    name.title(), len(fallback),
                )
                results[name] = fallback
        else:
            existing = _load_existing(cfg["output"])
            existing_set = set(existing)
            new_slugs = [s for s in slugs if s not in existing_set]

            if new_slugs:
                logger.info(
                    "%s: validating %d new slugs (skipping %d already known)",
                    name.title(), len(new_slugs), len(existing_set),
                )
                validated_new = asyncio.run(validate_slugs(name, new_slugs))
                results[name] = sorted(set(existing) | set(validated_new))
                logger.info(
                    "%s: final count %d (%d existing + %d validated new)",
                    name.title(), len(results[name]), len(existing), len(validated_new),
                )
            else:
                results[name] = slugs

    client.close()

    # Save results — never overwrite with empty data
    for name in names:
        cfg = ATS_PLATFORMS[name]
        slugs = results[name]
        if slugs:
            cfg["output"].write_text(
                json.dumps(slugs, indent=2), encoding="utf-8",
            )

    # Summary
    total = sum(len(results[n]) for n in names)
    num_platforms = len(names)
    print()
    print("=" * 60)
    print(f"  Common Crawl index used: {crawl_id}")
    print("=" * 60)
    for name in names:
        count = len(results[name])
        pages = page_counts.get(name, 0)
        print(f"  {name.title():16s}  {pages} pages fetched, {count:>6,} unique slugs")
    print(f"  {'Total':16s}  {total:>6,} companies across {num_platforms} ATS platforms")
    print("-" * 60)
    file_names = [f"{n}_companies.json" for n in names]
    print(f"  Files saved: {', '.join(file_names)}")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover ATS companies via Common Crawl CDX API",
    )
    parser.add_argument(
        "--crawl",
        default=None,
        help="Specific Common Crawl index to query (e.g. CC-MAIN-2026-12). "
             "If omitted, the latest available index is used automatically.",
    )
    args = parser.parse_args()
    run_discovery(crawl_override=args.crawl)


if __name__ == "__main__":
    main()
