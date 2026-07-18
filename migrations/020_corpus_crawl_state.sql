-- migrations/020_corpus_crawl_state.sql
-- P1.2 (FORM_ENGINE_DESIGN.md §3.6a): tracks per-job crawl progress for the
-- corpus harvester (pipeline/corpus_harvester.py) so re-running the script
-- resumes instead of re-crawling everything. One row per (job_id, ats)
-- attempted; absence of a row means "never attempted." extraction_status
-- mirrors §3.6a's page-level enum, plus likely_blocked (added during
-- implementation planning) so a Greenhouse/WAF block gets reported as a
-- block instead of silently misreported as ordinary no_form_found/error
-- noise in the corpus's coverage signal.

CREATE TABLE IF NOT EXISTS corpus_crawl_state (
    job_id             TEXT        NOT NULL,
    ats                TEXT        NOT NULL,
    extraction_status  TEXT        NOT NULL CHECK (extraction_status IN (
                           'ok', 'partial', 'no_form_found',
                           'apply_button_clicked_no_form',
                           'shadow_dom_unhandled', 'iframe_unhandled',
                           'likely_blocked', 'error'
                       )),
    manifest_line_ref  TEXT,       -- path/offset into the JSONL manifest for this run
    page_html_path     TEXT,       -- gzipped sidecar path, mirrors the manifest record
    crawled_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    harvester_version  TEXT        NOT NULL,
    error_detail       TEXT,       -- populated only when extraction_status = 'error' or 'likely_blocked'
    PRIMARY KEY (job_id, ats),
    FOREIGN KEY (job_id, ats) REFERENCES jobs (job_id, ats) ON DELETE CASCADE
);

-- Resume query support: filter to un-attempted / error rows for retry.
CREATE INDEX IF NOT EXISTS idx_corpus_crawl_state_status ON corpus_crawl_state (extraction_status);
