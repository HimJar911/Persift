"""One-time backfill: re-derive description/categories/years_of_experience
for existing Lever job rows now that pollers/lever.py folds `lists[]`
content into the text it classifies (previously only `descriptionPlain`
was used — confirmed live to be ~26% of a posting's total available text,
missing an explicit "N years of experience" phrase in 35.7% of sampled
postings). See pollers/lever.py's _lists_to_text docstring for the full
finding.

Re-polls each tracked Lever company live rather than reading stale local
data. Chunked per decisions/0006 (unbounded batch writes hung the pipeline
for 13+ min at full volume once already).

Run: python -m scripts.backfill_lever_lists
"""

import asyncio
import logging
import os

import asyncpg
import httpx
from dotenv import load_dotenv

from pollers.filter import assign_categories
from pollers.lever import _lists_to_text
from pollers.seniority import extract_years_of_experience

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_CHUNK_SIZE = 2000
_CONCURRENCY = 15


def _chunks(items: list, size: int = _CHUNK_SIZE):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _to_pg_array(items: list[str]) -> str:
    """Encode a Python list of category strings as a Postgres array literal.

    Same workaround as db.py's _to_pg_array: unnest(text[][]) flattens all
    dimensions, so a per-row categories list is passed as a text literal
    inside a text[] and cast back to text[] in the query.
    """
    if not items:
        return "{}"
    escaped = ['"' + item.replace("\\", "\\\\").replace('"', '\\"') + '"' for item in items]
    return "{" + ",".join(escaped) + "}"


async def main() -> None:
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=2, max_size=10)
    try:
        slugs = [r["company_slug"] for r in await pool.fetch(
            "SELECT DISTINCT company_slug FROM jobs WHERE ats='lever'"
        )]
        logger.info("Lever: %d companies to re-poll for lists backfill", len(slugs))

        updates: list[tuple[str, str, list[str], int | None, int | None]] = []
        sem = asyncio.Semaphore(_CONCURRENCY)
        async with httpx.AsyncClient(timeout=25) as client:
            async def fetch(slug: str) -> None:
                try:
                    async with sem:
                        r = await client.get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
                        if r.status_code != 200:
                            return
                        data = r.json()
                except Exception:
                    return
                if not isinstance(data, list):
                    return
                for job in data:
                    job_id = str(job.get("id", ""))
                    title = job.get("text", "")
                    if not job_id or not title:
                        continue
                    description_plain = job.get("descriptionPlain", "")
                    lists_text = _lists_to_text(job.get("lists"))
                    if not lists_text:
                        continue  # nothing new to add for this job
                    full_text = f"{description_plain}\n\n{lists_text}"
                    categories = assign_categories(title, full_text)
                    yoe_min, yoe_max = extract_years_of_experience(title, full_text)
                    updates.append((job_id, full_text, _to_pg_array(categories), yoe_min, yoe_max))
            await asyncio.gather(*[fetch(s) for s in slugs])

        logger.info("Lever: %d jobs with lists[] content to backfill", len(updates))

        applied = 0
        async with pool.acquire() as conn:
            for chunk in _chunks(updates):
                await conn.execute(
                    """
                    UPDATE jobs AS j
                    SET description = c.description,
                        categories = c.categories::text[],
                        years_of_experience_min = c.yoe_min,
                        years_of_experience_max = c.yoe_max
                    FROM (
                        SELECT unnest($1::text[]) AS job_id,
                               unnest($2::text[]) AS description,
                               unnest($3::text[]) AS categories,
                               unnest($4::smallint[]) AS yoe_min,
                               unnest($5::smallint[]) AS yoe_max
                    ) AS c
                    WHERE j.job_id = c.job_id AND j.ats = 'lever'
                    """,
                    [u[0] for u in chunk],
                    [u[1] for u in chunk],
                    [u[2] for u in chunk],
                    [u[3] for u in chunk],
                    [u[4] for u in chunk],
                )
                applied += len(chunk)
                logger.info("Lever lists backfill: applied %d/%d", applied, len(updates))

        logger.info("Lever lists backfill complete, %d rows updated", applied)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
