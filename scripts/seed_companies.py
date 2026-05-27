"""scripts/seed_companies.py — one-time seed of the companies table.

Reads the 4 JSON company-slug files, detects cross-ATS slug matches,
assigns shared canonical_company_ids to matches, then bulk-inserts into
the companies table.

Safe to re-run: INSERT ... ON CONFLICT (slug, ats) DO NOTHING.

Usage:
    python scripts/seed_companies.py
"""

import asyncio
import json
import sys
import uuid
from collections import defaultdict
from pathlib import Path

import asyncpg

# Resolve project root regardless of where the script is invoked from
PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from config import DATABASE_URL  # noqa: E402 — path insert must come first

# ─────────────────────────────────────────────────────────────────────────────
# File map
# ─────────────────────────────────────────────────────────────────────────────
ATS_FILES: dict[str, Path] = {
    "greenhouse":      PROJECT_DIR / "greenhouse_companies.json",
    "ashby":           PROJECT_DIR / "ashby_companies.json",
    "lever":           PROJECT_DIR / "lever_companies.json",
    "smartrecruiters": PROJECT_DIR / "smartrecruiters_companies.json",
}


def load_slugs() -> dict[str, list[str]]:
    """Load slug lists from JSON files. Exits if any file is missing."""
    result: dict[str, list[str]] = {}
    for ats, path in ATS_FILES.items():
        if not path.exists():
            print(f"ERROR: {path} not found — run discover_companies.py first")
            sys.exit(1)
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            print(f"ERROR: {path} is not a JSON array")
            sys.exit(1)
        result[ats] = [s for s in data if isinstance(s, str) and s.strip()]
        print(f"  Loaded {len(result[ats]):>6,} slugs from {path.name}")
    return result


def find_cross_ats_matches(
    slugs_by_ats: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Return slug → [ats, ...] for slugs that appear in more than one ATS."""
    slug_to_ats: dict[str, list[str]] = defaultdict(list)
    for ats, slugs in slugs_by_ats.items():
        for slug in slugs:
            slug_to_ats[slug].append(ats)

    return {
        slug: ats_list
        for slug, ats_list in slug_to_ats.items()
        if len(ats_list) > 1
    }


def assign_canonical_ids(
    slugs_by_ats: dict[str, list[str]],
    cross_ats_matches: dict[str, list[str]],
) -> dict[str, uuid.UUID]:
    """Return (slug, ats) → canonical_company_id.

    Cross-ATS matches share one UUID; all others get their own.
    """
    # Pre-assign one UUID per cross-ATS slug (shared across its ATSes)
    shared: dict[str, uuid.UUID] = {
        slug: uuid.uuid4() for slug in cross_ats_matches
    }

    canonical: dict[tuple[str, str], uuid.UUID] = {}
    for ats, slugs in slugs_by_ats.items():
        for slug in slugs:
            if slug in shared:
                canonical[(slug, ats)] = shared[slug]
            else:
                canonical[(slug, ats)] = uuid.uuid4()

    return canonical


async def seed(conn: asyncpg.Connection, slugs_by_ats: dict[str, list[str]]) -> dict[str, int]:
    """Insert all rows. Returns count of rows inserted per ATS."""
    cross_ats = find_cross_ats_matches(slugs_by_ats)
    canonical_ids = assign_canonical_ids(slugs_by_ats, cross_ats)

    inserted_counts: dict[str, int] = {}

    for ats, slugs in slugs_by_ats.items():
        rows_inserted = 0
        for slug in slugs:
            cid = canonical_ids[(slug, ats)]
            is_cross = slug in cross_ats
            tag = await conn.execute(
                """
                INSERT INTO companies (
                    canonical_company_id,
                    ats,
                    slug,
                    name,
                    is_active,
                    consecutive_failures,
                    match_method,
                    match_confidence,
                    discovered_via,
                    discovered_at,
                    created_at
                ) VALUES (
                    $1, $2, $3,
                    $3,       -- name defaults to slug until enriched
                    TRUE,
                    0,
                    $4,
                    'high',
                    'direct_seed',
                    NOW(),
                    NOW()
                )
                ON CONFLICT (slug, ats) DO NOTHING
                """,
                cid,
                ats,
                slug,
                "slug_matched" if is_cross else "seed_manual",
            )
            # asyncpg execute() returns e.g. "INSERT 0 1" or "INSERT 0 0"
            if tag.split()[-1] == "1":
                rows_inserted += 1

        inserted_counts[ats] = rows_inserted

    return inserted_counts, cross_ats, canonical_ids


async def main() -> None:
    print("\n=== Persift company seed ===\n")

    print("Loading JSON files:")
    slugs_by_ats = load_slugs()
    total_slugs = sum(len(v) for v in slugs_by_ats.values())
    print(f"\n  Total slugs across all files: {total_slugs:,}\n")

    print(f"Connecting to Postgres...")
    conn = await asyncpg.connect(DATABASE_URL)

    try:
        inserted_counts, cross_ats, canonical_ids = await seed(conn, slugs_by_ats)
    finally:
        await conn.close()

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  SEED COMPLETE")
    print("=" * 60)

    print("\n  Rows inserted per ATS:")
    for ats, count in inserted_counts.items():
        total_for_ats = len(slugs_by_ats[ats])
        skipped = total_for_ats - count
        skip_note = f" ({skipped} skipped — already existed)" if skipped else ""
        print(f"    {ats:18s}  {count:>6,} inserted{skip_note}")

    total_inserted = sum(inserted_counts.values())
    total_canonical = len({cid for cid in canonical_ids.values()})
    print(f"\n  Total rows inserted:           {total_inserted:>6,}")
    print(f"  Unique canonical_company_ids:  {total_canonical:>6,}")
    print(f"  Cross-ATS slug matches found:  {len(cross_ats):>6,}")

    if cross_ats:
        print("\n  Cross-ATS matches (shared canonical_company_id):")
        print(f"  {'Slug':<35}  ATSes")
        print(f"  {'-'*35}  {'-----'}")
        for slug in sorted(cross_ats):
            ats_list = ", ".join(sorted(cross_ats[slug]))
            print(f"  {slug:<35}  {ats_list}")
    else:
        print("\n  No cross-ATS slug matches found.")

    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
