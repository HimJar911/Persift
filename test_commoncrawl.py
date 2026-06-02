"""
CommonCrawl test — single company (billgo.com).
Approach A: DuckDB columnar index parquet on S3 (anonymous)
Approach B: CDX HTTP API (fallback if S3 auth fails)
Either way, ends with a byte-range WARC fetch + HTML print.
"""

import gzip
import json
import sys
import httpx
import duckdb

CRAWL   = "CC-MAIN-2026-21"
DOMAIN  = "billgo.com"
CC_BASE = "https://data.commoncrawl.org"
CDX_API = f"https://index.commoncrawl.org/{CRAWL}-index"

warc_filename = offset = length = matched_url = None


# ---------------------------------------------------------------------------
# Approach A — DuckDB columnar index
# ---------------------------------------------------------------------------

def try_duckdb() -> tuple | None:
    print(f"[A] DuckDB columnar index query for {DOMAIN} ...")
    try:
        con = duckdb.connect()
        con.execute("INSTALL httpfs; LOAD httpfs;")

        # Anonymous S3 access: path-style disables SigV4 signing on public buckets
        con.execute("SET s3_region='us-east-1';")
        con.execute("SET s3_url_style='path';")
        con.execute("SET s3_access_key_id='';")
        con.execute("SET s3_secret_access_key='';")
        con.execute("SET s3_session_token='';")

        # Restrict to the specific crawl partition to avoid scanning all crawls
        parquet = (
            "s3://commoncrawl/cc-index/table/cc-main/warc/"
            f"crawl={CRAWL}/subset=warc/*.parquet"
        )
        query = f"""
            SELECT url, warc_filename, warc_record_offset, warc_record_length
            FROM read_parquet('{parquet}', hive_partitioning=true)
            WHERE url_host_registered_domain = '{DOMAIN}'
              AND (url_path LIKE '%career%' OR url_path LIKE '%job%')
            LIMIT 5
        """
        print(f"    Parquet path: {parquet}")
        rows = con.execute(query).fetchall()
        if not rows:
            print(f"    No results in parquet index.")
            return None
        print(f"    Found {len(rows)} row(s):")
        for r in rows:
            print(f"      {r[0]}  |  offset={r[2]}  len={r[3]}")
        return rows[0]
    except Exception as e:
        print(f"    DuckDB failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Approach B — CDX HTTP API (fallback)
# ---------------------------------------------------------------------------

def try_cdx() -> tuple | None:
    print(f"\n[B] CDX API fallback for {DOMAIN} ...")
    params = {
        "url":       f"{DOMAIN}/*",
        "output":    "json",
        "fl":        "url,filename,offset,length,status,mime",
        "filter":    ["status:200", "mime:text/html"],
        "matchType": "prefix",
        "limit":     "20",
    }
    try:
        resp = httpx.get(CDX_API, params=params, timeout=30)
        print(f"    CDX status: {resp.status_code}")
        if resp.status_code != 200:
            print(f"    CDX request failed.")
            return None
    except Exception as e:
        print(f"    CDX request error: {e}")
        return None

    # CDX returns one JSON object per line
    records = []
    for line in resp.text.strip().splitlines():
        try:
            records.append(json.loads(line))
        except Exception:
            continue

    print(f"    Total CDX records: {len(records)}")
    if not records:
        print(f"    No records found via CDX API.")
        return None

    # Filter for career/job URLs
    career_records = [
        r for r in records
        if "career" in r.get("url", "").lower() or "job" in r.get("url", "").lower()
    ]
    print(f"    Career/job records: {len(career_records)}")

    # Fall back to any record if no career-specific ones
    target_records = career_records if career_records else records
    best = target_records[0]

    print(f"    Selected URL    : {best['url']}")
    print(f"    WARC filename   : {best['filename']}")
    print(f"    Offset / Length : {best['offset']} / {best['length']}")

    return best["url"], best["filename"], int(best["offset"]), int(best["length"])


# ---------------------------------------------------------------------------
# Run approaches in order
# ---------------------------------------------------------------------------

result = try_duckdb()
if result is None:
    result = try_cdx()

if result is None:
    print("\nBoth approaches failed. Cannot proceed to WARC fetch.")
    sys.exit(1)

matched_url, warc_filename, offset, length = result


# ---------------------------------------------------------------------------
# Step 2 — Fetch WARC byte range
# ---------------------------------------------------------------------------

warc_url   = f"{CC_BASE}/{warc_filename}"
range_hdr  = f"bytes={offset}-{offset + length - 1}"

print(f"\n[C] Fetching WARC byte range ...")
print(f"    URL   : {warc_url}")
print(f"    Range : {range_hdr}  ({length:,} bytes)")

try:
    resp = httpx.get(
        warc_url,
        headers={"Range": range_hdr},
        timeout=60,
        follow_redirects=True,
    )
    print(f"    HTTP  : {resp.status_code}  ({len(resp.content):,} bytes received)")
except Exception as e:
    print(f"    Fetch error: {e}")
    sys.exit(1)

if resp.status_code not in (200, 206):
    print(f"    Unexpected status. Aborting.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Step 3 — Decompress and extract HTML body
# ---------------------------------------------------------------------------

print(f"\n[D] Decompressing and parsing WARC record ...")

try:
    raw = gzip.decompress(resp.content)
except Exception as e:
    print(f"    gzip failed ({e}) — using raw bytes")
    raw = resp.content

text = raw.decode("utf-8", errors="replace")
print(f"    Decompressed size : {len(text):,} chars")

# WARC structure: WARC headers -> blank line -> HTTP headers -> blank line -> HTML body
# Find the second \r\n\r\n (end of HTTP response headers)
first_sep = text.find("\r\n\r\n")
if first_sep != -1:
    after_warc_headers = text[first_sep + 4:]
    second_sep = after_warc_headers.find("\r\n\r\n")
    if second_sep != -1:
        html = after_warc_headers[second_sep + 4:]
    else:
        html = after_warc_headers
else:
    html = text

print(f"    HTML body length  : {len(html):,} chars")
print()
print("=" * 64)
print(f"  Source URL : {matched_url}")
print("=" * 64)
print(html[:2000])
print("=" * 64)
