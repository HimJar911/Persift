"""Regenerate the compact corpus at full volume: original 767-job snapshot
(frozen, unchanged) + the second-run's 17,391 `likely_real`-triaged records
(corpus_analysis/triage_real_vs_junk_resolved.json), converted from the
manifest's rich field schema into the same compact schema auto_cluster.py /
oc_compact_full.json already use.

Deliberately does NOT touch or overwrite oc_compact_full.json — that file
stays the frozen snapshot the existing (ci, fi)-keyed decisions (now also
backfilled with stable job_id/field_id_hash keys, see
backfill_stable_keys.py) apply to. This writes a NEW file,
oc_compact_full_v2.json, whose array order/indices are independent and not
assumed stable across future regenerations either — anything keyed against
THIS file should use the stable (job_id, field_id_hash, occurrence_index)
key, not raw (ci, fi), from the start.

Compact schema per field (matches auto_cluster.py's expectations exactly):
  h        = field_id_hash
  tag, itype (=input_type), htype (=html_type), name, id, ac (=autocomplete),
  role, req (=required), vis (=visible), label, lstrat (=label_strategy),
  section, nearby (=nearby_text), opts (=options), desc (=description),
  placeholder

Run: python corpus_analysis/build_compact_corpus_v2.py
Reads:  corpus_analysis/oc_compact_full.json (original 767, unchanged source)
        corpus_analysis/triage_real_vs_junk_resolved.json (likely_real job_ids)
        corpus/manifest.jsonl (full field data for the new records)
Writes: corpus_analysis/oc_compact_full_v2.json
"""

import json
from pathlib import Path

from original_corpus_junk_exclusions import EXCLUDED_ORIGINAL_JOB_IDS

BASE = Path(__file__).parent
ORIGINAL_COMPACT = BASE / "oc_compact_full.json"
TRIAGE_RESOLVED = BASE / "triage_real_vs_junk_resolved.json"
MANIFEST = BASE.parent / "corpus" / "manifest.jsonl"
OUT = BASE / "oc_compact_full_v2.json"


def to_compact_field(field):
    sem = field.get("field_semantics", {})
    return {
        "h": field["field_id_hash"],
        "tag": field.get("tag", ""),
        "itype": field.get("input_type", ""),
        "htype": field.get("html_type", ""),
        "name": field.get("name", ""),
        "id": field.get("id", ""),
        "ac": field.get("autocomplete", ""),
        "role": field.get("role", ""),
        "req": field.get("required", False),
        "vis": field.get("visible", True),
        "label": sem.get("label", ""),
        "lstrat": sem.get("label_strategy"),
        "section": sem.get("section"),
        "nearby": sem.get("nearby_text", ""),
        "opts": sem.get("options"),
        "desc": sem.get("description", ""),
        "placeholder": sem.get("placeholder", ""),
    }


def main():
    with open(ORIGINAL_COMPACT, encoding="utf-8") as f:
        original_companies_raw = json.load(f)
    original_companies = [
        c for c in original_companies_raw
        if c["job_id"] not in EXCLUDED_ORIGINAL_JOB_IDS
    ]
    excluded_count = len(original_companies_raw) - len(original_companies)
    original_job_ids = {c["job_id"] for c in original_companies_raw}
    print(f"original compact corpus: {len(original_companies_raw)} companies, "
          f"{excluded_count} excluded as junk (see original_corpus_junk_exclusions.py), "
          f"{len(original_companies)} kept")

    with open(TRIAGE_RESOLVED, encoding="utf-8") as f:
        triage = json.load(f)
    likely_real_job_ids = {r["job_id"] for r in triage["likely_real"]}
    # The original 767's job_ids were never through this triage pass (the
    # second run's LEFT JOIN only crawled NEW jobs) — but guard anyway in
    # case of accidental overlap, so we never double-add a company.
    new_job_ids = likely_real_job_ids - original_job_ids
    print(f"likely_real from second run: {len(likely_real_job_ids)} "
          f"({len(new_job_ids)} not already in original corpus)")

    new_companies = []
    seen_job_ids_in_manifest = set()
    with open(MANIFEST, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            job_id = rec["job_id"]
            if job_id not in new_job_ids:
                continue
            if job_id in seen_job_ids_in_manifest:
                continue  # manifest could in principle have dup lines; keep first
            seen_job_ids_in_manifest.add(job_id)
            new_companies.append({
                "company": rec.get("company_name") or job_id,
                "job_id": job_id,
                "fields": [to_compact_field(f) for f in rec.get("fields", [])],
            })

    print(f"converted {len(new_companies)} new company records from manifest")

    full = original_companies + new_companies
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(full, f)

    total_fields = sum(len(c["fields"]) for c in full)
    print(f"wrote {OUT}: {len(full)} companies, {total_fields} fields total")


if __name__ == "__main__":
    main()
