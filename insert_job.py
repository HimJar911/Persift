import asyncio, asyncpg, os

async def run():
    conn = await asyncpg.connect(os.environ['DATABASE_URL'])
    await conn.execute("""
        INSERT INTO jobs (job_id, ats, company_slug, company_name, title, apply_url, categories, experience_level, work_model, h1b_sponsored, posted_at, sources)
        VALUES ('5153686008', 'greenhouse', 'internshiplist2000', 'Internship List', 'Software Engineer Intern', 'https://job-boards.greenhouse.io/internshiplist2000/jobs/5153686008', '{software_engineering}', 'intern', 'hybrid', 'Not Sure', 0, '{greenhouse}')
        ON CONFLICT DO NOTHING
    """)
    await conn.execute("""
        INSERT INTO user_jobs (user_id, job_id, job_ats, status)
        VALUES ('46e66cfa-e625-4ffc-b8dc-7bf75e21db26', '5153686008', 'greenhouse', 'applying')
        ON CONFLICT DO NOTHING
    """)
    print('Done')
    await conn.close()

asyncio.run(run())
