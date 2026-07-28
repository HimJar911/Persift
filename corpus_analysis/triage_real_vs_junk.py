"""Bucket the ~19,100 newly-harvested (second-run) manifest records into
likely_real / likely_junk / uncertain, WITHOUT dropping anything — every
record's bucket + evidence gets written out, so nothing is silently
discarded (see corpus_analysis README / STATE.md plan: junk-page filtering
must be a triage, not a hard drop, because a wrong filter call would lose a
real edge-case form).

Why this exists: corpus/README.md "Scope and known limitations" documents
that a real share of `ok`-status second-run pages land on a generic
job-search/listing page instead of the actual application form (an
unfixed apply_url construction issue for some Greenhouse-embed postings).
The first run's hand-classification pass naturally excluded these; the
second run has no such filtering yet.

Heuristic (verified against real sampled pages before being trusted, not
guessed — see verification notes below):
  - PRIMARY signal: absence of a resume/CV upload field. Checked against a
    stratified sample (thin-field-count pages, thick-but-no-resume pages,
    a same-company pair where one posting was real and its sibling was a
    listing page) — every no-resume record sampled and read via raw HTML
    was confirmed to be a job-board search/filter/listing page, not a real
    application form (nav search boxes, "Filter jobs" sections, language
    switchers, cookie-consent widgets). Zero false positives found in the
    verification sample (see corpus_analysis/README.md triage QA notes).
  - Field count is NOT used as the primary signal — a same-company pair
    (Bayada) showed a 15-field page can still be a pure listing page
    (every field tagged section="Filter jobs"), so a naive count threshold
    alone would have produced false negatives the resume-field check
    catches instead.
  - `uncertain`: has_resume is False but field count is unusually high
    (>15) for a listing page, OR has_resume is True but field count is
    unusually low (<=5) for a real form — these combinations weren't seen
    in the verification sample and need a human read before trusting
    either bucket assignment.

Run: python corpus_analysis/triage_real_vs_junk.py
Reads:  corpus/manifest.jsonl (all records, both harvest runs)
Writes: corpus_analysis/triage_real_vs_junk.json
        {"likely_real": [...job_ids...], "likely_junk": [...job_ids...],
         "uncertain": [...job_ids...], "counts": {...}}
        Every job_id also gets its evidence (field_count, has_resume)
        recorded, not just the bucket name, so a human reviewing
        `uncertain` (or auditing `likely_junk`) doesn't need to re-derive it.
"""

import json
from pathlib import Path

MANIFEST = Path(__file__).parent.parent / "corpus" / "manifest.jsonl"
OUT = Path(__file__).parent / "triage_real_vs_junk.json"

# Bag of low-cost lexical checks for "this field is a resume/CV upload."
_RESUME_TERMS = ("resume", "cv", "curriculum vitae")


def has_resume_field(fields):
    for fl in fields:
        if fl.get("input_type") == "file":
            return True
        sem = fl.get("field_semantics", {})
        label = (sem.get("label") or "").lower()
        name = (fl.get("name") or "").lower()
        fid = (fl.get("id") or "").lower()
        if any(term in label for term in _RESUME_TERMS):
            return True
        if any(term in name for term in _RESUME_TERMS):
            return True
        if any(term in fid for term in _RESUME_TERMS):
            return True
    return False


def bucket(field_count, resume_present):
    if resume_present:
        if field_count <= 5:
            return "uncertain"  # real-form marker present but suspiciously thin
        return "likely_real"
    else:
        if field_count > 15:
            return "uncertain"  # no resume field but a lot of fields — unexpected shape
        return "likely_junk"


def main():
    buckets = {"likely_real": [], "likely_junk": [], "uncertain": []}
    non_ok_skipped = 0

    with open(MANIFEST, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec["extraction_status"] != "ok":
                # Non-ok records (error/likely_blocked/no_form_found/
                # apply_button_clicked_no_form) are a separate, already
                # explicit status — not part of this real-vs-junk triage.
                non_ok_skipped += 1
                continue

            fields = rec.get("fields", [])
            field_count = len(fields)
            resume_present = has_resume_field(fields)
            b = bucket(field_count, resume_present)

            buckets[b].append({
                "job_id": rec["job_id"],
                "company_name": rec.get("company_name", ""),
                "crawled_url": rec.get("crawled_url", ""),
                "field_count": field_count,
                "has_resume_field": resume_present,
            })

    counts = {k: len(v) for k, v in buckets.items()}
    counts["non_ok_skipped"] = non_ok_skipped

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({**buckets, "counts": counts}, f, indent=2)

    print("Bucket counts:", counts)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
