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
import psycopg2

from config import (
    GREENHOUSE_FALLBACK_SLUGS, LEVER_FALLBACK_SLUGS, ASHBY_FALLBACK_SLUGS,
    SMARTRECRUITERS_FALLBACK_SLUGS,
    DATABASE_URL,
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
        # Greenhouse has two live frontend domains — job-boards.greenhouse.io
        # is the newer one and carries ~4x boards.greenhouse.io's Common Crawl
        # volume (confirmed CC-MAIN-2026-25: 4 pages vs 1). Both use the same
        # /{slug}/... URL shape, so one regex covers both once the domain is
        # substituted in per-domain at crawl time (see discover_ats).
        "domains": ["boards.greenhouse.io", "job-boards.greenhouse.io"],
        "output": PROJECT_DIR / "greenhouse_companies.json",
        "slug_regex_template": r"^https?://{domain}/([^/?#]+)",
        "fallback": GREENHOUSE_FALLBACK_SLUGS,
    },
    "lever": {
        "domains": ["jobs.lever.co"],
        "output": PROJECT_DIR / "lever_companies.json",
        "slug_regex_template": r"^https?://{domain}/([^/?#]+)",
        "fallback": LEVER_FALLBACK_SLUGS,
        "timeout": _LEVER_TIMEOUT,
        "retry_limit": _LEVER_RETRY_LIMIT,
        "page_delay": _LEVER_PAGE_DELAY,
        "merge_existing": True,
    },
    "ashby": {
        "domains": ["jobs.ashbyhq.com"],
        "output": PROJECT_DIR / "ashby_companies.json",
        "slug_regex_template": r"^https?://{domain}/([^/?#]+)",
        "fallback": ASHBY_FALLBACK_SLUGS,
    },
    "smartrecruiters": {
        "domains": ["jobs.smartrecruiters.com"],
        "output": PROJECT_DIR / "smartrecruiters_companies.json",
        "slug_regex_template": r"^https?://{domain}/([^/?#]+)",
        "fallback": SMARTRECRUITERS_FALLBACK_SLUGS,
    },
}


# ---------------------------------------------------------------------------
# Step 1: Discover latest crawl index
# ---------------------------------------------------------------------------

_PROBE_DOMAIN = "boards.greenhouse.io"
_PROBE_TIMEOUT = 20   # short — just a liveness check, fail fast
_MAX_PROBE_ATTEMPTS = 3

# How many recent monthly indexes to union by default. Common Crawl only sees
# a company's board if some page linking to it got crawled that month, so any
# single month misses companies visible in others — see get_recent_cdx_apis.
_DEFAULT_NUM_MONTHS = 6


def get_recent_cdx_apis(
    client: httpx.Client, num_months: int, crawl_override: str | None
) -> list[tuple[str, str]]:
    """Return up to *num_months* ready (crawl_id, cdx_api_url) pairs, newest first.

    Common Crawl is a general web crawl, not an ATS directory — it only sees a
    company's job-board URL if some other page linked to it and got crawled
    that month. Any single month misses companies that were unlinked/uncrawled
    that cycle but visible in an earlier or later one, so querying only the
    latest index (the old behavior) systematically undercounts. Querying the
    last *num_months* indexes and unioning results (done by the caller, via
    the same existing-slug merge run_discovery already does per platform)
    recovers companies that only appeared in some months, not all.

    If crawl_override is given, returns exactly that one crawl (unchanged
    single-crawl behavior, e.g. for reproducing a past run).
    """
    logger.info("Fetching Common Crawl index list from %s", COLLINFO_URL)
    resp = client.get(COLLINFO_URL, timeout=30)
    resp.raise_for_status()
    crawls = resp.json()

    if not crawls:
        raise RuntimeError("Common Crawl collinfo.json returned empty list")

    crawls.sort(key=lambda c: c["id"], reverse=True)

    if crawl_override:
        for c in crawls:
            if c["id"] == crawl_override:
                logger.info("Using specified crawl: %s", c["id"])
                return [(c["id"], c["cdx-api"])]
        raise RuntimeError(
            f"Crawl {crawl_override!r} not found. "
            f"Latest available: {crawls[0]['id']}"
        )

    # Probe more candidates than num_months needs, in case some are still
    # being indexed (same tolerance as the single-crawl probe above).
    max_attempts = num_months + _MAX_PROBE_ATTEMPTS
    ready: list[tuple[str, str]] = []
    for c in crawls[:max_attempts]:
        crawl_id = c["id"]
        cdx_api = c["cdx-api"]
        logger.info("Probing crawl %s...", crawl_id)
        pages = _get_num_pages(
            client, cdx_api, _PROBE_DOMAIN, "probe",
            timeout=_PROBE_TIMEOUT, retry_limit=1,
        )
        if pages is not None:
            logger.info("Crawl %s ready (%d pages for probe domain)", crawl_id, pages)
            ready.append((crawl_id, cdx_api))
            if len(ready) >= num_months:
                break
        else:
            logger.warning("Crawl %s not ready — skipping", crawl_id)

    if not ready:
        tried = [c["id"] for c in crawls[:max_attempts]]
        raise RuntimeError(
            f"No ready Common Crawl index found after probing {max_attempts} crawls. "
            f"Tried: {tried}"
        )
    return ready


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

    Queries every domain in cfg["domains"] (a platform can have more than one
    live frontend, e.g. Greenhouse's boards.greenhouse.io + newer
    job-boards.greenhouse.io) and merges the results.

    Returns (sorted deduplicated list of slugs or None, total pages_fetched).
    None means every configured domain's CDX query was unreachable.
    """
    cfg = ATS_PLATFORMS[ats_name]
    domains = cfg["domains"]
    regex_template = cfg["slug_regex_template"]
    label = ats_name.title()
    slug_filter = cfg.get("slug_filter")

    # Per-platform overrides
    timeout = cfg.get("timeout", _REQUEST_TIMEOUT)
    retry_limit = cfg.get("retry_limit", _RETRY_LIMIT)
    page_delay = cfg.get("page_delay", _PAGE_DELAY)

    all_slugs: list[str] = []
    total_pages_fetched = 0
    any_domain_reachable = False

    for domain in domains:
        domain_label = f"{label} ({domain})"
        regex = re.compile(regex_template.format(domain=re.escape(domain)))

        logger.info("%s: checking page count...", domain_label)
        num_pages = _get_num_pages(
            client, cdx_api, domain, domain_label,
            timeout=timeout, retry_limit=retry_limit,
        )
        if num_pages is None:
            logger.error("%s: could not determine page count — skipping domain", domain_label)
            continue
        any_domain_reachable = True
        if num_pages == 0:
            logger.warning("%s: CDX returned 0 pages", domain_label)
            continue

        logger.info("%s: %d pages to fetch", domain_label, num_pages)

        pages_ok = 0
        for page in range(num_pages):
            print(f"  {domain_label}: fetching page {page + 1}/{num_pages}...", flush=True)
            page_slugs = _fetch_page_slugs(
                client, cdx_api, domain, regex, page, domain_label,
                timeout=timeout, retry_limit=retry_limit,
                slug_filter=slug_filter,
            )
            all_slugs.extend(page_slugs)
            if page_slugs:
                pages_ok += 1

            # Politeness delay between pages (skip after last page)
            if page < num_pages - 1:
                time.sleep(page_delay)

        total_pages_fetched += num_pages
        logger.info("%s: %d/%d pages fetched", domain_label, pages_ok, num_pages)

    if not any_domain_reachable:
        logger.error("%s: could not reach any configured domain — skipping", label)
        return None, 0

    # Deduplicate and sort (same slug can legitimately appear under multiple
    # domains, e.g. a company mid-migration between Greenhouse frontends)
    unique = sorted(set(all_slugs))
    logger.info(
        "%s: %d unique slugs across %d domain(s) (from %d raw matches)",
        label, len(unique), len(domains), len(all_slugs),
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
# Revalidation — re-check existing slugs against live APIs
# ---------------------------------------------------------------------------

async def revalidate_existing_slugs(names: list[str]) -> None:
    """Validate all slugs currently saved in the JSON files. Remove dead ones in-place."""
    for name in names:
        cfg = ATS_PLATFORMS[name]
        existing = _load_existing(cfg["output"])
        if not existing:
            logger.info("%s: no existing slugs to revalidate", name.title())
            continue

        valid = await validate_slugs(name, existing)
        removed = len(existing) - len(valid)
        logger.info(
            "%s: revalidation done — %d removed, %d active",
            name.title(), removed, len(valid),
        )
        if removed:
            cfg["output"].write_text(json.dumps(sorted(valid), indent=2), encoding="utf-8")
            _upsert_companies_to_db(name, sorted(valid))


# ---------------------------------------------------------------------------
# Step 5 & 6: Save, fallback, and summary
# ---------------------------------------------------------------------------

def _upsert_companies_to_db(ats_name: str, slugs: list[str]) -> None:
    """Insert new slugs into the companies table. Skips rows that already exist."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO companies
                        (slug, ats, canonical_company_id, is_active,
                         discovered_via, discovered_at, match_method, match_confidence)
                    VALUES
                        (%s, %s, gen_random_uuid(), TRUE,
                         'direct_seed', NOW(), 'new', 'unverified')
                    ON CONFLICT (slug, ats) DO NOTHING
                    """,
                    [(slug, ats_name) for slug in slugs],
                )
            conn.commit()
            logger.info("%s: upserted %d slugs into companies table", ats_name.title(), len(slugs))
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("%s: DB upsert failed — %s", ats_name.title(), exc)


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


def run_discovery(
    crawl_override: str | None = None,
    revalidate: bool = False,
    num_months: int = _DEFAULT_NUM_MONTHS,
) -> None:
    """Discover companies for all ATS platforms and save results.

    Queries *num_months* recent Common Crawl indexes (not just the latest —
    see get_recent_cdx_apis for why) and unions the slugs each one turns up
    per platform before validating/saving once at the end.
    """
    client = httpx.Client()

    try:
        crawl_apis = get_recent_cdx_apis(client, num_months, crawl_override)
    except Exception as exc:
        logger.error("Failed to get Common Crawl index info: %s", exc)
        logger.warning("Keeping existing company files unchanged")
        client.close()
        return

    names = list(ATS_PLATFORMS.keys())
    raw_slugs: dict[str, set[str]] = {name: set() for name in names}
    page_counts: dict[str, int] = {name: 0 for name in names}
    any_crawl_hit: dict[str, bool] = {name: False for name in names}

    # Run sequentially — polite to Common Crawl servers. Each crawl adds
    # whatever new slugs it turns up on top of what earlier crawls (and the
    # existing saved files) already found.
    for crawl_id, cdx_api in crawl_apis:
        logger.info("=== Querying crawl %s ===", crawl_id)
        for name in names:
            slugs, num_pages = discover_ats(client, name, cdx_api)
            page_counts[name] += num_pages
            if slugs:
                raw_slugs[name].update(slugs)
                any_crawl_hit[name] = True

    client.close()

    results: dict[str, list[str]] = {}
    for name in names:
        cfg = ATS_PLATFORMS[name]
        slugs = sorted(raw_slugs[name])

        if not any_crawl_hit[name]:
            # Every crawl for this platform was unreachable or empty — keep existing.
            existing = _load_existing(cfg["output"])
            if existing:
                logger.warning(
                    "%s: no crawl returned data — keeping existing file (%d companies)",
                    name.title(), len(existing),
                )
                results[name] = existing
            else:
                fallback = list(cfg["fallback"])
                logger.warning(
                    "%s: no crawl returned data and no existing file — using hardcoded fallback (%d companies)",
                    name.title(), len(fallback),
                )
                results[name] = fallback
        else:
            existing = _load_existing(cfg["output"])
            existing_set = set(existing)
            new_slugs = [s for s in slugs if s not in existing_set]

            if new_slugs:
                logger.info(
                    "%s: validating %d new slugs across %d crawl(s) (skipping %d already known)",
                    name.title(), len(new_slugs), len(crawl_apis), len(existing_set),
                )
                validated_new = asyncio.run(validate_slugs(name, new_slugs))
                results[name] = sorted(set(existing) | set(validated_new))
                logger.info(
                    "%s: final count %d (%d existing + %d validated new)",
                    name.title(), len(results[name]), len(existing), len(validated_new),
                )
            else:
                results[name] = slugs

    # Save results — never overwrite with empty data
    for name in names:
        cfg = ATS_PLATFORMS[name]
        slugs = results[name]
        if slugs:
            cfg["output"].write_text(
                json.dumps(slugs, indent=2), encoding="utf-8",
            )
            _upsert_companies_to_db(name, slugs)

    # Revalidation phase — runs after CDX save, checks all slugs including pre-existing ones
    if revalidate:
        logger.info("Starting revalidation — checking all saved slugs against live APIs")
        asyncio.run(revalidate_existing_slugs(names))

    # Summary
    total = sum(len(results[n]) for n in names)
    num_platforms = len(names)
    crawl_ids = [c[0] for c in crawl_apis]
    print()
    print("=" * 60)
    print(f"  Common Crawl indexes used ({len(crawl_ids)}): {', '.join(crawl_ids)}")
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
        help="Specific Common Crawl index to query (e.g. CC-MAIN-2026-12), instead "
             "of the recent-months union. Overrides --months (queries exactly one).",
    )
    parser.add_argument(
        "--months",
        type=int,
        default=_DEFAULT_NUM_MONTHS,
        help=f"Number of recent monthly Common Crawl indexes to union (default {_DEFAULT_NUM_MONTHS}). "
             "A single month misses companies that were unlinked/uncrawled that cycle but "
             "visible in another — see get_recent_cdx_apis.",
    )
    parser.add_argument(
        "--revalidate",
        action="store_true",
        help="After CDX discovery, re-validate all slugs in the saved JSON files "
             "against their live ATS APIs and remove any that no longer respond with 200/403.",
    )
    args = parser.parse_args()
    run_discovery(crawl_override=args.crawl, revalidate=args.revalidate, num_months=args.months)


if __name__ == "__main__":
    main()
