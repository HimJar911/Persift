"""Worker A: reads discovery_staging rows, runs ATS detection cascade, writes to companies."""

import asyncio
import logging
import re

import httpx

from db import get_pool

logger = logging.getLogger(__name__)

WORKER_VERSION = "1.0.0"
_BATCH_SIZE = 500
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
}

_HREF_SRC_RE = re.compile(r'(?:href|src)=["\']([^"\'>\s]+)["\']', re.IGNORECASE)

# Strips common legal suffixes before generating slug candidates.
_SUFFIX_RE = re.compile(
    r'[\s,]+(?:inc\.?|incorporated|llc|ltd\.?|limited|corp\.?|corporation|'
    r'co\.?|plc|gmbh|ag|sa|technologies|technology|tech|solutions|'
    r'group|holdings|services|international|systems|global)\s*$',
    re.IGNORECASE,
)


def _slug_candidates(company_name: str) -> list[str]:
    """Generate slug variants from a company name to match against companies.slug.

    Produces hyphenated and concatenated forms, with and without common
    business suffixes, so 'Stripe, Inc.' matches slug 'stripe'.
    """
    base = company_name.lower().strip()
    stripped = _SUFFIX_RE.sub("", base).strip()
    candidates: set[str] = set()
    for name in (base, stripped):
        if not name:
            continue
        candidates.add(re.sub(r"[^a-z0-9]+", "-", name).strip("-"))
        candidates.add(re.sub(r"[^a-z0-9]+", "", name))
    return [c for c in candidates if c]


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


def _detect_stage1(apply_url: str | None) -> tuple[str, str] | None:
    """URL pattern match. Returns (ats, slug) or None. Zero network cost."""
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


async def _detect_stage2(
    apply_url: str,
    session: httpx.AsyncClient,
    sem: asyncio.Semaphore,
) -> tuple[str, str | None] | None:
    """Fetch the page, find ATS fingerprints, try to extract a slug from embedded URLs.

    Returns (ats, slug), (ats, None) if ATS found but slug unclear, or None.
    No DB connection is held during the fetch.
    """
    async with sem:
        try:
            resp = await session.get(
                apply_url,
                timeout=_HTTP_TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": _USER_AGENT},
            )
            html = resp.text
        except Exception:
            return None

    detected_ats: str | None = None
    for ats_name, fingerprints in ATS_HTML_FINGERPRINTS.items():
        if any(fp in html for fp in fingerprints):
            detected_ats = ats_name
            break

    if detected_ats is None:
        return None

    # Extract slug from href/src URLs in the page
    for fragment in _HREF_SRC_RE.findall(html):
        result = _detect_stage1(fragment)
        if result is not None:
            found_ats, slug = result
            if found_ats == detected_ats:
                return detected_ats, slug

    return detected_ats, None


async def _upsert_company(ats: str, slug: str, conn) -> str:
    """Insert company if new; return canonical_company_id in all cases."""
    row = await conn.fetchrow(
        """
        INSERT INTO companies
            (slug, ats, canonical_company_id, is_active,
             discovered_via, discovered_at, match_method, match_confidence)
        VALUES
            ($1, $2, gen_random_uuid(), TRUE,
             'jobright_seeded', NOW(), 'new', 'unverified')
        ON CONFLICT (slug, ats) DO NOTHING
        RETURNING canonical_company_id
        """,
        slug, ats,
    )
    if row:
        return str(row["canonical_company_id"])
    existing = await conn.fetchrow(
        "SELECT canonical_company_id FROM companies WHERE slug = $1 AND ats = $2",
        slug, ats,
    )
    return str(existing["canonical_company_id"])


async def _mark_staging_row(
    row_id: int,
    result: str,
    canonical_id: str | None,
    conn,
) -> None:
    await conn.execute(
        """
        UPDATE discovery_staging
        SET processed = TRUE,
            processed_at = NOW(),
            result = $2,
            result_canonical_company_id = $3::uuid,
            worker_version = $4
        WHERE id = $1
        """,
        row_id, result, canonical_id, WORKER_VERSION,
    )


async def _queue_manual_review(
    row_id: int,
    apply_url: str | None,
    company_name: str | None,
    bucket: str,
    conn,
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


async def _process_row(row, pool, counters: dict) -> None:
    # Stages 1+2 (URL pattern + HTML fingerprint) are suspended — Jobright bulk
    # API does not expose apply URLs and unauthenticated jobs/info pages omit them.
    # Re-enable when a reliable apply_url source is available.
    row_id = row["id"]
    company_name = row["company_name"]

    try:
        async with pool.acquire() as conn:
            if company_name:
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

            # Step 3 — no match, queue for manual review
            await _queue_manual_review(row_id, None, company_name, "unknown_ats", conn)
            counters["queued_manual"] += 1

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


async def run_discovery_cycle() -> None:
    logger.info("=== Starting discovery cycle ===")
    await _ensure_manual_review_table()

    pool = get_pool()
    totals = {"added": 0, "already_known": 0, "queued_manual": 0, "failed": 0}
    batch_num = 0

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
            *[_process_row(row, pool, counters) for row in rows],
            return_exceptions=True,
        )

        for k in totals:
            totals[k] += counters[k]

        logger.info(
            "Batch %d complete — added: %d | already_known: %d | queued_manual: %d | failed: %d",
            batch_num,
            counters["added"],
            counters["already_known"],
            counters["queued_manual"],
            counters["failed"],
        )

    if batch_num == 0:
        logger.info("=== Discovery cycle complete — no unprocessed rows ===")
        return

    total_rows = sum(totals.values())
    logger.info(
        "Discovery cycle complete — %s companies analyzed | %s already tracked | %s newly identified",
        f"{total_rows:,}",
        f"{totals['already_known']:,}",
        f"{totals['queued_manual']:,}",
    )
