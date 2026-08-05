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

    # pronouns — value matches real Greenhouse combobox option text
    # (verified live against Myriad360 job 8646163002), resolveValue()
    # fuzzy-matches this against whatever wording each form actually uses.
    existing["pronouns"] = "He/Him/His"

    await conn.execute(
        "UPDATE users SET application_settings = $1::jsonb WHERE tier = $2",
        json.dumps(existing), "pro",
    )

    # visa_type/needs_sponsorship are COLUMNS (migration 016), not JSONB keys
    await conn.execute(
        "UPDATE users SET visa_type = $1, needs_sponsorship = $2 WHERE tier = $3",
        "F1", True, "pro",
    )

    # work_models must match jobs.work_model's real casing ("Remote",
    # "Hybrid", "On Site") — matcher.py's filter #2 does case-sensitive
    # set membership, so lowercase values silently hard-filter out every
    # real job (found live: preferences had ["remote","hybrid"], which
    # matched 0 of the 8,900+/1,871+/1,471+ real On Site/Hybrid/Remote rows).
    await conn.execute(
        """
        UPDATE users
        SET preferences = jsonb_set(preferences, '{work_models}', $1::jsonb)
        WHERE tier = $2
        """,
        json.dumps(["Remote", "Hybrid", "On Site"]), "pro",
    )
    print("Done — visa_type=F1, needs_sponsorship=True, immigration support answer added, "
          "pronouns=He/Him/His, work_models=[Remote, Hybrid, On Site]")
    await conn.close()


asyncio.run(run())
