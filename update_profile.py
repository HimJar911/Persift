import asyncio, asyncpg, os, json


async def run():
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    settings = json.dumps(
        {
            "first_name": "Himanshu",
            "last_name": "Jarodiya",
            "phone": "6025666701",
            "linkedin_url": "https://REDACTED-LINKEDIN",
            "location_city": "REDACTED",
        }
    )
    await conn.execute(
        "UPDATE users SET application_settings = $1 WHERE tier = $2", settings, "pro"
    )
    print("Done")
    await conn.close()


asyncio.run(run())
