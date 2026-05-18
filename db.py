"""Seen-jobs database layer.

Supports two backends controlled by config.DB_BACKEND:
  - "sqlite"   — local SQLite file, no external dependencies (default for local dev)
  - "dynamodb" — AWS DynamoDB, serverless and durable (for production on AWS)
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from config import DB_BACKEND

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# SQLite backend
# ──────────────────────────────────────────────────────────────────────────────

async def _sqlite_init() -> None:
    import aiosqlite
    from config import DB_PATH
    async with aiosqlite.connect(Path(__file__).parent / DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS seen_jobs (
                id          TEXT NOT NULL,
                ats         TEXT NOT NULL,
                company_slug TEXT NOT NULL,
                title       TEXT NOT NULL,
                url         TEXT NOT NULL,
                first_seen_at DATETIME NOT NULL,
                PRIMARY KEY (id, ats)
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_seen_jobs_ats ON seen_jobs (ats)"
        )
        await db.commit()
    logger.info("SQLite database ready (%s)", DB_PATH)


async def _sqlite_filter_new_ids(candidate_ids: list[str], ats: str) -> set[str]:
    import aiosqlite
    from config import DB_PATH
    if not candidate_ids:
        return set()
    existing: set[str] = set()
    async with aiosqlite.connect(Path(__file__).parent / DB_PATH) as db:
        for i in range(0, len(candidate_ids), 500):
            batch = candidate_ids[i : i + 500]
            placeholders = ",".join("?" for _ in batch)
            cursor = await db.execute(
                f"SELECT id FROM seen_jobs WHERE ats = ? AND id IN ({placeholders})",
                [ats, *batch],
            )
            rows = await cursor.fetchall()
            existing.update(row[0] for row in rows)
    return set(candidate_ids) - existing


async def _sqlite_mark_seen_batch(jobs: list[dict]) -> None:
    import aiosqlite
    from config import DB_PATH
    if not jobs:
        return
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(Path(__file__).parent / DB_PATH) as db:
        await db.executemany(
            """INSERT OR IGNORE INTO seen_jobs (id, ats, company_slug, title, url, first_seen_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [(j["job_id"], j["ats"], j["company_slug"], j["title"], j["apply_url"], now) for j in jobs],
        )
        await db.commit()
    logger.info("Marked %d jobs as seen", len(jobs))


# ──────────────────────────────────────────────────────────────────────────────
# DynamoDB backend
# ──────────────────────────────────────────────────────────────────────────────

def _dynamo_client_kwargs() -> dict:
    from config import AWS_REGION, DYNAMODB_ENDPOINT
    kwargs: dict = {"region_name": AWS_REGION}
    if DYNAMODB_ENDPOINT:
        kwargs["endpoint_url"] = DYNAMODB_ENDPOINT
    return kwargs


def _pk(ats: str, job_id: str) -> str:
    return f"{ats}#{job_id}"


async def _dynamo_init() -> None:
    import aioboto3
    from botocore.exceptions import ClientError
    from config import DYNAMODB_TABLE
    session = aioboto3.Session()
    async with session.client("dynamodb", **_dynamo_client_kwargs()) as client:
        try:
            await client.describe_table(TableName=DYNAMODB_TABLE)
            logger.info("DynamoDB table '%s' exists", DYNAMODB_TABLE)
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ResourceNotFoundException":
                await client.create_table(
                    TableName=DYNAMODB_TABLE,
                    KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
                    AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
                    BillingMode="PAY_PER_REQUEST",
                )
                waiter = client.get_waiter("table_exists")
                await waiter.wait(TableName=DYNAMODB_TABLE)
                logger.info("Created DynamoDB table '%s'", DYNAMODB_TABLE)
            else:
                raise


async def _dynamo_filter_new_ids(candidate_ids: list[str], ats: str) -> set[str]:
    import aioboto3
    from config import DYNAMODB_TABLE
    if not candidate_ids:
        return set()
    existing: set[str] = set()
    session = aioboto3.Session()
    async with session.client("dynamodb", **_dynamo_client_kwargs()) as client:
        for i in range(0, len(candidate_ids), 100):
            batch = candidate_ids[i : i + 100]
            keys = [{"pk": {"S": _pk(ats, jid)}} for jid in batch]
            resp = await client.batch_get_item(
                RequestItems={DYNAMODB_TABLE: {"Keys": keys, "ProjectionExpression": "pk"}}
            )
            for item in resp.get("Responses", {}).get(DYNAMODB_TABLE, []):
                existing.add(item["pk"]["S"].split("#", 1)[1])
            unprocessed = resp.get("UnprocessedKeys", {})
            while unprocessed.get(DYNAMODB_TABLE):
                resp = await client.batch_get_item(RequestItems=unprocessed)
                for item in resp.get("Responses", {}).get(DYNAMODB_TABLE, []):
                    existing.add(item["pk"]["S"].split("#", 1)[1])
                unprocessed = resp.get("UnprocessedKeys", {})
    return set(candidate_ids) - existing


async def _dynamo_mark_seen_batch(jobs: list[dict]) -> None:
    import aioboto3
    from config import DYNAMODB_TABLE
    if not jobs:
        return
    now = datetime.now(timezone.utc).isoformat()
    session = aioboto3.Session()
    async with session.client("dynamodb", **_dynamo_client_kwargs()) as client:
        for i in range(0, len(jobs), 25):
            batch = jobs[i : i + 25]
            items = [
                {"PutRequest": {"Item": {
                    "pk": {"S": _pk(j["ats"], j["job_id"])},
                    "ats": {"S": j["ats"]},
                    "job_id": {"S": j["job_id"]},
                    "company_slug": {"S": j["company_slug"]},
                    "title": {"S": j["title"]},
                    "url": {"S": j["apply_url"]},
                    "first_seen_at": {"S": now},
                }}}
                for j in batch
            ]
            resp = await client.batch_write_item(RequestItems={DYNAMODB_TABLE: items})
            unprocessed = resp.get("UnprocessedItems", {})
            while unprocessed.get(DYNAMODB_TABLE):
                resp = await client.batch_write_item(RequestItems=unprocessed)
                unprocessed = resp.get("UnprocessedItems", {})
    logger.info("Marked %d jobs as seen", len(jobs))


# ──────────────────────────────────────────────────────────────────────────────
# Public API — delegates to the configured backend
# ──────────────────────────────────────────────────────────────────────────────

async def init_db() -> None:
    if DB_BACKEND == "dynamodb":
        await _dynamo_init()
    else:
        await _sqlite_init()


async def filter_new_ids(candidate_ids: list[str], ats: str) -> set[str]:
    if DB_BACKEND == "dynamodb":
        return await _dynamo_filter_new_ids(candidate_ids, ats)
    return await _sqlite_filter_new_ids(candidate_ids, ats)


async def mark_seen_batch(jobs: list[dict]) -> None:
    if DB_BACKEND == "dynamodb":
        await _dynamo_mark_seen_batch(jobs)
    else:
        await _sqlite_mark_seen_batch(jobs)
