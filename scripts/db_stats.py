import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

url = os.environ["RENDER_DATABASE_URL"]
conn = psycopg2.connect(url)
cur = conn.cursor()

# 1. Companies discovered via fingerprint
cur.execute("SELECT COUNT(*) FROM companies WHERE discovered_via = 'fingerprint'")
fingerprint_count = cur.fetchone()[0]

# 2. discovery_staging totals split by processed
cur.execute("SELECT processed, COUNT(*) FROM discovery_staging GROUP BY processed ORDER BY processed")
staging_rows = cur.fetchall()

# 3. manual_review_queue split by bucket
cur.execute("SELECT bucket, COUNT(*) FROM manual_review_queue GROUP BY bucket ORDER BY bucket")
queue_rows = cur.fetchall()

# 4. Jobright poller state — last run time and cursor
cur.execute("""
    SELECT last_run_at, cursor->>'since_ms' AS since_ms
    FROM poller_state
    WHERE poller = 'jobright'
""")
jobright_state = cur.fetchone()

# 5. Jobs in the jobs table from Jobright
cur.execute("SELECT COUNT(*) FROM jobs WHERE ats = 'jobright'")
jobright_jobs_count = cur.fetchone()[0]

cur.close()
conn.close()

print("=== Persift Render DB Stats ===\n")

print(f"1. Companies with discovered_via='fingerprint': {fingerprint_count}")

print("\n2. discovery_staging rows:")
total_staging = 0
for processed, count in staging_rows:
    label = "processed" if processed else "unprocessed"
    print(f"   {label}: {count:,}")
    total_staging += count
print(f"   total:       {total_staging:,}")

print("\n3. manual_review_queue rows by bucket:")
total_queue = 0
for bucket, count in queue_rows:
    print(f"   {bucket}: {count:,}")
    total_queue += count
if not queue_rows:
    print("   (empty)")
print(f"   total: {total_queue:,}")

print("\n4. Jobright poller state:")
if jobright_state:
    last_run_at, since_ms = jobright_state
    print(f"   last_run_at: {last_run_at}")
    print(f"   cursor since_ms: {since_ms}")
else:
    print("   (no state row — poller has never run)")

print(f"\n5. Jobs in jobs table from Jobright: {jobright_jobs_count:,}")
