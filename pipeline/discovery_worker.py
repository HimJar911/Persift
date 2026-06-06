"""Worker A: reads discovery_staging rows, runs ATS detection cascade, writes to companies."""

import asyncio
import json
import logging
import math
import re
from urllib.parse import urlparse

import httpx

from db import get_pool

logger = logging.getLogger(__name__)

WORKER_VERSION = "1.1.0"
_BATCH_SIZE = 50
_HTTP_TIMEOUT = 10
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

ATS_URL_PATTERNS = {
    "greenhouse":       re.compile(r"boards\.greenhouse\.io/([^/?#]+)"),
    "lever":            re.compile(r"jobs\.lever\.co/([^/?#]+)"),
    "ashby":            re.compile(r"jobs\.ashbyhq\.com/([^/?#]+)"),
    "smartrecruiters":  re.compile(r"jobs\.smartrecruiters\.com/([^/?#]+)"),
    "workday":          re.compile(r"([^.]+)\.myworkdayjobs\.com"),
    "icims":            re.compile(r"([^.]+)\.icims\.com"),
    "jobvite":          re.compile(r"jobs\.jobvite\.com/([^/?#]+)"),
    "greenhouse_embed": re.compile(r"boards-api\.greenhouse\.io/v1/boards/([^/?#]+)"),
}

ATS_HTML_FINGERPRINTS = {
    "greenhouse":      ["boards.greenhouse.io", "grnh.se"],
    "lever":           ["jobs.lever.co", "lever.co/apply"],
    "ashby":           ["jobs.ashbyhq.com", "ashbyhq.com"],
    "smartrecruiters": ["jobs.smartrecruiters.com"],
    "workday":         ["myworkdayjobs.com", "workday.com/en-US/pages"],
    "icims":           [".icims.com/jobs/"],
    "jobvite":         ["jobs.jobvite.com"],
    "bamboohr":        ["bamboohr.com/jobs/", "app.bamboohr.com"],
}

# ATSes with active pollers — fingerprinted companies go into companies table as result='added'.
_POLLED_ATS = {"ashby", "greenhouse", "lever", "smartrecruiters"}

_HREF_SRC_RE = re.compile(r'(?:href|src)=["\']([^"\'>\s]+)["\']', re.IGNORECASE)
_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', re.DOTALL
)

_CAREER_PATHS = ["/careers", "/jobs", "/career", "/join", "/work-with-us"]
_JOBRIGHT_INFO_URL = "https://jobright.ai/jobs/info/{job_id}"

_SUFFIX_RE = re.compile(
    r'[\s,]+(?:inc\.?|incorporated|llc|ltd\.?|limited|corp\.?|corporation|'
    r'co\.?|plc|gmbh|ag|sa|technologies|technology|tech|solutions|'
    r'group|holdings|services|international|systems|global)\s*$',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------

def _slug_candidates(company_name: str) -> list[str]:
    """Generate slug variants from a company name to match against companies.slug."""
    base = company_name.lower().strip()
    stripped = _SUFFIX_RE.sub("", base).strip()
    candidates: set[str] = set()
    for name in (base, stripped):
        if not name:
            continue
        candidates.add(re.sub(r"[^a-z0-9]+", "-", name).strip("-"))
        candidates.add(re.sub(r"[^a-z0-9]+", "", name))
    return [c for c in candidates if c]


def _normalize_domain(raw_url: str) -> str | None:
    """Return bare domain from a URL string (strips scheme and www), or None."""
    raw_url = raw_url.strip()
    if not raw_url:
        return None
    if not raw_url.startswith("http"):
        raw_url = "https://" + raw_url
    try:
        netloc = urlparse(raw_url).netloc
        if not netloc:
            return None
        return netloc.removeprefix("www.").lower() or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# HTTP helpers — all consume the shared semaphore
# ---------------------------------------------------------------------------

async def _fetch_company_domain(
    job_id: str,
    company_name: str,
    session: httpx.AsyncClient,
    sem: asyncio.Semaphore,
) -> str | None:
    """Fetch Jobright job-info page, parse __NEXT_DATA__, return bare company domain."""
    raw_id = job_id.removeprefix("jobright_")
    url = _JOBRIGHT_INFO_URL.format(job_id=raw_id)
    async with sem:
        try:
            resp = await session.get(url, timeout=_HTTP_TIMEOUT, headers={"User-Agent": _USER_AGENT})
            resp.raise_for_status()
            html = resp.text
        except Exception as exc:
            logger.warning("[Worker A] %s — stage=domain_fetch http_error: %s: %s", company_name, type(exc).__name__, exc)
            return None

    m = _NEXT_DATA_RE.search(html)
    if not m:
        logger.warning("[Worker A] %s — stage=domain_fetch __NEXT_DATA__ not found in page", company_name)
        return None

    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError as exc:
        logger.warning("[Worker A] %s — stage=domain_fetch __NEXT_DATA__ json parse error: %s", company_name, exc)
        return None

    try:
        company_url = data["props"]["pageProps"]["dataSource"]["companyResult"]["companyURL"]
    except (KeyError, TypeError) as exc:
        logger.warning("[Worker A] %s — stage=domain_fetch companyURL key missing: %s", company_name, exc)
        return None

    if not company_url:
        logger.warning("[Worker A] %s — stage=domain_fetch companyURL is empty/null", company_name)
        return None

    return _normalize_domain(company_url)


async def _find_career_page(
    domain: str,
    company_name: str,
    session: httpx.AsyncClient,
    sem: asyncio.Semaphore,
) -> tuple[str, str] | None:
    """Try common career page paths on a domain. Returns (url, html) at first 200."""
    for path in _CAREER_PATHS:
        url = f"https://{domain}{path}"
        async with sem:
            try:
                resp = await session.get(
                    url, timeout=_HTTP_TIMEOUT,
                    follow_redirects=True,
                    headers={"User-Agent": _USER_AGENT},
                )
            except Exception as exc:
                logger.debug("[Worker A] %s — stage=career_page path=%s error: %s: %s", company_name, path, type(exc).__name__, exc)
                continue
        if resp.status_code == 200:
            return url, resp.text
        logger.debug("[Worker A] %s — stage=career_page path=%s status=%d", company_name, path, resp.status_code)
    logger.warning("[Worker A] %s — stage=career_page domain=%s no path returned 200", company_name, domain)
    return None


# ---------------------------------------------------------------------------
# ATS fingerprinting
# ---------------------------------------------------------------------------

def _detect_stage1(apply_url: str | None) -> tuple[str, str] | None:
    """URL pattern match against known ATS URL shapes. Zero network cost."""
    if not apply_url:
        return None
    for ats_name, pattern in ATS_URL_PATTERNS.items():
        m = pattern.search(apply_url)
        if m:
            slug = m.group(1).lower().strip().rstrip("/")
            if slug:
                canonical_ats = "greenhouse" if ats_name == "greenhouse_embed" else ats_name
                return canonical_ats, slug
    return None


def _fingerprint_html(html: str) -> tuple[str, str | None] | None:
    """Scan HTML for ATS fingerprints and try to extract the slug from embedded URLs.

    Returns (ats, slug), (ats, None) if ATS found but slug unclear, or None.
    """
    detected_ats: str | None = None
    for ats_name, fingerprints in ATS_HTML_FINGERPRINTS.items():
        if any(fp in html for fp in fingerprints):
            detected_ats = ats_name
            break
    if detected_ats is None:
        return None
    for fragment in _HREF_SRC_RE.findall(html):
        result = _detect_stage1(fragment)
        if result and result[0] == detected_ats:
            return detected_ats, result[1]
    return detected_ats, None


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _ensure_manual_review_table() -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS manual_review_queue (
                id            SERIAL PRIMARY KEY,
                apply_url     TEXT,
                company_name  TEXT,
                staged_job_id INT UNIQUE REFERENCES discovery_staging(id),
                bucket        TEXT CHECK (bucket IN ('known_ats_unclear_slug', 'unknown_ats')),
                created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                resolved      BOOLEAN NOT NULL DEFAULT FALSE
            )
        """)


async def _upsert_company(ats: str, slug: str, company_name: str, conn) -> str:
    """Insert company if new; return canonical_company_id in all cases."""
    row = await conn.fetchrow(
        """
        INSERT INTO companies
            (slug, ats, canonical_company_id, is_active, company_name,
             discovered_via, discovered_at, match_method, match_confidence)
        VALUES
            ($1, $2, gen_random_uuid(), TRUE, $3,
             'fingerprint', NOW(), 'career_page_fingerprint', 'high')
        ON CONFLICT (slug, ats) DO NOTHING
        RETURNING canonical_company_id
        """,
        slug, ats, company_name,
    )
    if row:
        return str(row["canonical_company_id"])
    existing = await conn.fetchrow(
        "SELECT canonical_company_id FROM companies WHERE slug = $1 AND ats = $2",
        slug, ats,
    )
    return str(existing["canonical_company_id"])


async def _mark_staging_row(
    row_id: int, result: str, canonical_id: str | None, conn,
) -> None:
    await conn.execute(
        """
        UPDATE discovery_staging
        SET processed = TRUE, processed_at = NOW(),
            result = $2, result_canonical_company_id = $3::uuid,
            worker_version = $4
        WHERE id = $1
        """,
        row_id, result, canonical_id, WORKER_VERSION,
    )


async def _queue_manual_review(
    row_id: int, apply_url: str | None, company_name: str | None,
    bucket: str, conn,
) -> None:
    await conn.execute(
        """
        INSERT INTO manual_review_queue (apply_url, company_name, staged_job_id, bucket)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (staged_job_id) DO NOTHING
        """,
        apply_url, company_name, row_id, bucket,
    )
    await _mark_staging_row(row_id, "queued_manual", None, conn)


# ---------------------------------------------------------------------------
# Row processor
# ---------------------------------------------------------------------------

async def _process_row(
    row,
    pool,
    session: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    counters: dict,
) -> None:
    row_id = row["id"]
    company_name = row["company_name"]
    job_id = row["job_id"]

    try:
        # ── Slug matching (no network I/O, connection released before fingerprinting) ──
        if company_name:
            async with pool.acquire() as conn:
                # Step 1 — exact company_name match (case-insensitive)
                existing = await conn.fetchrow(
                    "SELECT canonical_company_id FROM companies "
                    "WHERE LOWER(company_name) = LOWER($1) LIMIT 1",
                    company_name,
                )
                if existing:
                    await _mark_staging_row(
                        row_id, "already_known", str(existing["canonical_company_id"]), conn
                    )
                    counters["already_known"] += 1
                    return

                # Step 2 — slug candidates derived from company name, any ATS
                candidates = _slug_candidates(company_name)
                existing = await conn.fetchrow(
                    "SELECT canonical_company_id FROM companies "
                    "WHERE slug = ANY($1::text[]) LIMIT 1",
                    candidates,
                )
                if existing:
                    await _mark_staging_row(
                        row_id, "already_known", str(existing["canonical_company_id"]), conn
                    )
                    counters["already_known"] += 1
                    return

        # ── Fingerprinting cascade (I/O-heavy; no DB connection held) ───────────────

        # Stage 1 — fetch company domain from Jobright __NEXT_DATA__
        domain = await _fetch_company_domain(job_id, company_name, session, sem)

        if not domain:
            async with pool.acquire() as conn:
                await _queue_manual_review(row_id, None, company_name, "unknown_ats", conn)
            counters["queued_manual"] += 1
            return

        # Stage 2 — find career page
        career_result = await _find_career_page(domain, company_name, session, sem)

        if not career_result:
            async with pool.acquire() as conn:
                await _queue_manual_review(row_id, None, company_name, "unknown_ats", conn)
            counters["queued_manual"] += 1
            return

        career_url, html = career_result

        # Stage 3 — grep HTML for ATS signatures
        fp = _fingerprint_html(html)

        if not fp:
            logger.warning("[Worker A] %s — stage=ats_detect domain=%s no ATS signature in career page HTML", company_name, domain)
            async with pool.acquire() as conn:
                await _queue_manual_review(row_id, career_url, company_name, "unknown_ats", conn)
            counters["queued_manual"] += 1
            return

        detected_ats, extracted_slug = fp

        # Stage 5 — ATS identified but not one we poll (workday, bamboohr, icims, etc.)
        if detected_ats not in _POLLED_ATS:
            logger.warning("[Worker A] %s — stage=ats_detect domain=%s ats=%s not in polled set", company_name, domain, detected_ats)
            async with pool.acquire() as conn:
                await _queue_manual_review(
                    row_id, career_url, company_name, "known_ats_unclear_slug", conn
                )
            counters["queued_manual"] += 1
            return

        # Stage 4 — polled ATS: derive slug and add to companies
        slug_list = _slug_candidates(company_name) if company_name else []
        slug = extracted_slug or (slug_list[0] if slug_list else None)

        if not slug:
            logger.warning("[Worker A] %s — stage=slug_extract domain=%s ats=%s could not derive slug", company_name, domain, detected_ats)
            async with pool.acquire() as conn:
                await _queue_manual_review(
                    row_id, career_url, company_name, "known_ats_unclear_slug", conn
                )
            counters["queued_manual"] += 1
            return

        async with pool.acquire() as conn:
            cid = await _upsert_company(detected_ats, slug, company_name or "", conn)
            await _mark_staging_row(row_id, "added", cid, conn)
        counters["added"] += 1
        logger.info("[Worker A] %s — added %s/%s", company_name, detected_ats, slug)

    except Exception as exc:
        logger.warning("Discovery: row %d failed — %s", row_id, exc)
        counters["failed"] += 1
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE discovery_staging
                    SET processed = TRUE, processed_at = NOW(),
                        result = 'failed', worker_version = $2
                    WHERE id = $1
                    """,
                    row_id, WORKER_VERSION,
                )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Cycle entry point
# ---------------------------------------------------------------------------

async def run_discovery_cycle() -> None:
    logger.info("=== Starting discovery cycle ===")
    await _ensure_manual_review_table()

    pool = get_pool()

    async with pool.acquire() as conn:
        unprocessed = await conn.fetchval(
            "SELECT COUNT(*) FROM discovery_staging WHERE processed = FALSE"
        )

    if not unprocessed:
        logger.info("=== Discovery cycle complete — no unprocessed rows ===")
        return

    total_batches = math.ceil(unprocessed / _BATCH_SIZE)
    totals = {"added": 0, "already_known": 0, "queued_manual": 0, "failed": 0}
    batch_num = 0

    sem = asyncio.Semaphore(10)

    async with httpx.AsyncClient() as session:
        while True:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, job_id, job_ats, company_name, apply_url
                    FROM discovery_staging
                    WHERE processed = FALSE
                    ORDER BY staged_at ASC
                    LIMIT $1
                    """,
                    _BATCH_SIZE,
                )

            if not rows:
                break

            batch_num += 1
            counters = {"added": 0, "already_known": 0, "queued_manual": 0, "failed": 0}

            await asyncio.gather(
                *[_process_row(row, pool, session, sem, counters) for row in rows],
                return_exceptions=True,
            )

            for k in totals:
                totals[k] += counters[k]

            print(
                f"[Batch {batch_num:2d}/{total_batches}]"
                f"  already_tracked: {counters['already_known']:4d}"
                f"  |  added: {counters['added']:4d}"
                f"  |  queued: {counters['queued_manual']:4d}",
                flush=True,
            )

    _HR = "━" * 62
    total_rows = sum(totals.values())
    print(_HR)
    print(f"  DISCOVERY COMPLETE")
    print(f"  {total_rows:,} companies analyzed")
    print(f"  {totals['already_known']:,} already tracked")
    print(f"  {totals['added']:,} newly added")
    print(f"  {totals['queued_manual']:,} queued for manual review")
    print(_HR, flush=True)
