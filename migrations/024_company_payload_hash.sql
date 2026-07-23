-- migrations/024_company_payload_hash.sql
-- Payload-change short-circuit for pollers, added after a Jul 22 incident:
-- a full re-poll's DB-write phase hung for 13+ minutes because
-- mark_seen_batch/repair_jobs_batch/repair_metadata_batch built unbounded
-- Python lists over an entire ATS's "seen" set (SmartRecruiters alone
-- returned 228K jobs in that poll cycle, nearly all already in the DB).
-- Chunking those batch writes (db.py's _BATCH_CHUNK_SIZE) fixes the
-- immediate crash; this column fixes the recurring cause — most companies'
-- job listings don't change between two 10-min polls, so re-parsing and
-- re-diffing their full response every cycle is wasted work. Storing a
-- hash of the last-seen raw response lets a poller skip a company entirely
-- (no parse, no filter_new_ids, no repair passes) when nothing changed.
--
-- Ashby additionally exposes a real HTTP ETag (verified live, Jul 22) —
-- last_response_etag stores that separately so pollers/ashby.py can send
-- If-None-Match and skip the download itself on a 304, not just skip
-- post-download processing.

ALTER TABLE companies ADD COLUMN IF NOT EXISTS last_payload_hash TEXT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS last_response_etag TEXT;

-- New company_poll_log outcome for the hash/etag short-circuit: distinct
-- from ok_zero_jobs (which means the company genuinely has no open roles)
-- so the dead-company/concentration analysis this table exists for doesn't
-- conflate "nothing changed" with "nothing posted."
ALTER TABLE company_poll_log DROP CONSTRAINT company_poll_log_outcome_check;
ALTER TABLE company_poll_log ADD CONSTRAINT company_poll_log_outcome_check
    CHECK (outcome IN (
        'ok_with_jobs', 'ok_zero_jobs', 'ok_unchanged', 'http_404',
        'http_429', 'http_4xx', 'http_5xx', 'timeout',
        'connection_error', 'other_exception'
    ));
