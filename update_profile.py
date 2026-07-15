import asyncio, asyncpg, os, json


async def run():
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])

    # Fetch existing settings and merge — never overwrite the whole blob
    row = await conn.fetchrow(
        "SELECT application_settings FROM users WHERE tier = $1", "pro"
    )
    existing = {}
    if row and row["application_settings"]:
        raw = row["application_settings"]
        existing = json.loads(raw) if isinstance(raw, str) else dict(raw)

    # Add/update immigration support answer in custom_answers list
    custom_answers = existing.get("custom_answers", [])
    if isinstance(custom_answers, str):
        custom_answers = json.loads(custom_answers)
    imm_key = "immigration support"
    if not any(a.get("questionKey") == imm_key for a in custom_answers):
        custom_answers.append({"questionKey": imm_key, "answer": "No"})
    existing["custom_answers"] = custom_answers

    await conn.execute(
        "UPDATE users SET application_settings = $1::jsonb WHERE tier = $2",
        json.dumps(existing), "pro",
    )

    # visa_type/needs_sponsorship are COLUMNS (migration 016), not JSONB keys
    await conn.execute(
        "UPDATE users SET visa_type = $1, needs_sponsorship = $2 WHERE tier = $3",
        "F1", True, "pro",
    )
    print("Done — visa_type=F1, needs_sponsorship=True, immigration support answer added")
    await conn.close()


asyncio.run(run())
