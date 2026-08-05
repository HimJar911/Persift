"""One-time fresh-DB bootstrap: applies migrations/*.sql in filename order.

Not a full migration framework (no rollback, no checksums) — but it does
track which files have been applied, in a small _schema_migrations table.
That tracking is required, not optional: several early migrations in this
repo (001, 007, 008, 010, 012 — confirmed by grep, not assumed) use plain
CREATE TABLE without IF NOT EXISTS, so a naive "just re-run every file"
approach fails on a second run. This script applies each migration inside
its own transaction and records it in _schema_migrations on success, so
re-running against a partially-migrated DB only applies what's missing.

Exists purely so a fresh Azure VM (or any fresh Postgres instance) doesn't
need every migration file applied by hand in order. See CLAUDE.md
"How to Run" for the rest of the fresh-environment bootstrap sequence this
fits into.
"""
import asyncio
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import asyncpg

from config import DATABASE_URL

MIGRATIONS_DIR = _REPO_ROOT / "migrations"

_TRACKING_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS _schema_migrations (
    filename    TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


async def run() -> None:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        print(f"No migration files found in {MIGRATIONS_DIR}")
        return

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(_TRACKING_TABLE_SQL)
        already_applied = {
            row["filename"]
            for row in await conn.fetch("SELECT filename FROM _schema_migrations")
        }

        applied_this_run = 0
        for path in files:
            if path.name in already_applied:
                print(f"Skipping {path.name} (already applied)")
                continue

            sql = path.read_text(encoding="utf-8")
            print(f"Applying {path.name} ...")
            try:
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO _schema_migrations (filename) VALUES ($1)",
                        path.name,
                    )
            except Exception as exc:
                print(f"FAILED on {path.name}: {exc}", file=sys.stderr)
                raise
            applied_this_run += 1

        print(
            f"Applied {applied_this_run} new migration file(s); "
            f"{len(files) - applied_this_run} already up to date."
        )
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
