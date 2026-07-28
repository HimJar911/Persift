"""One-time backfill: adds a stable (job_id, field_id_hash, occurrence_index,
page_content_hash) key to every existing (ci, fi)-keyed decision entry, plus a
decision_source provenance tag, without touching or invalidating the original
(ci, fi) fields.

Why: (ci, fi) indexes into oc_compact_full.json's array positions, which are
NOT guaranteed stable across a harvester re-run/corpus regeneration (see
corpus_analysis/README.md "Field key format"). job_id + field_id_hash (both
already present in oc_compact_full.json / corpus/manifest.jsonl) survive
regeneration. field_id_hash alone can collide within one page (confirmed:
andurilindustries has repeated-widget fields sharing a hash, e.g. a search
box's duplicated hidden/visible pair) so occurrence_index (the Nth field with
that hash on that page, in extraction order) disambiguates. page_content_hash
(sha1 of the gzipped sidecar HTML) is included so a job posting that gets
re-crawled with a changed form doesn't silently collide with a stale decision.

Run once: python corpus_analysis/backfill_stable_keys.py
Reads:  corpus_analysis/oc_compact_full.json (frozen snapshot, ci/fi source)
        corpus/pages/{job_id}.html.gz (for page_content_hash)
        every existing decision file listed in DECISION_FILES
Writes: corpus_analysis/stable_keys_backfill.json — one entry per (ci, fi)
        reference found across all decision files, each augmented with
        job_id, field_id_hash, occurrence_index, page_content_hash, and
        decision_source (inferred per source file below). Does NOT rewrite
        the original decision files — this is an additive lookup layer.
"""

import gzip
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).parent
COMPACT_CORPUS = BASE / "oc_compact_full.json"
PAGES_DIR = BASE.parent / "corpus" / "pages"

# (file, decision_source) — decision_source reflects how that file's
# decisions were actually reached, per corpus_analysis/README.md's pipeline
# account.
DECISION_FILES = [
    ("cluster_decisions.json", "existing_cluster"),
    ("triage_decisions.json", "existing_cluster"),
    ("manual_singleton_tags.json", "founder_verified"),
    ("manual_field_index_tags.json", "html_verified"),
    ("correction_department_location.json", "html_verified"),
]


def load_compact_corpus():
    with open(COMPACT_CORPUS, encoding="utf-8") as f:
        return json.load(f)


def page_content_hash(job_id):
    path = PAGES_DIR / f"{job_id}.html.gz"
    if not path.exists():
        return None
    with gzip.open(path, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()[:16]


def build_ci_fi_lookup(corpus):
    """(ci, fi) -> {job_id, field_id_hash, occurrence_index, page_content_hash}."""
    lookup = {}
    page_hash_cache = {}
    for ci, company in enumerate(corpus):
        job_id = company["job_id"]
        if job_id not in page_hash_cache:
            page_hash_cache[job_id] = page_content_hash(job_id)
        seen_hash_counts = {}
        for fi, field in enumerate(company["fields"]):
            h = field["h"]
            occurrence_index = seen_hash_counts.get(h, 0)
            seen_hash_counts[h] = occurrence_index + 1
            lookup[(ci, fi)] = {
                "job_id": job_id,
                "field_id_hash": h,
                "occurrence_index": occurrence_index,
                "page_content_hash": page_hash_cache[job_id],
            }
    return lookup


def extract_ci_fi_refs(fname, data):
    """Yield (ci, fi) pairs referenced by a decision file, in whatever shape
    that file uses. Returns a list of dicts: the original entry plus its
    (ci, fi)."""
    refs = []

    if fname in ("manual_singleton_tags.json", "manual_field_index_tags.json",
                 "correction_department_location.json"):
        # list of {"ci": int, "fi": int, ...}
        for entry in data:
            refs.append({"ci": entry["ci"], "fi": entry["fi"], "entry": entry})

    elif fname == "cluster_decisions.json":
        # {"confirm": {...}, "reject": {...}, "special": {...}} keyed by
        # "rule::key" -> category name. No direct (ci, fi) here — cluster
        # membership lives in clusters.json. Cross-reference it.
        clusters_path = BASE / "clusters.json"
        with open(clusters_path, encoding="utf-8") as f:
            clusters = json.load(f)["clusters"]
        cluster_by_rule_key = {
            f'{c["rule"]}::{c["key"]}': c for c in clusters
        }
        for bucket in ("confirm", "reject", "special"):
            for rule_key, category in data.get(bucket, {}).items():
                cluster = cluster_by_rule_key.get(rule_key)
                if not cluster:
                    continue
                for member in cluster["members"]:
                    refs.append({
                        "ci": member["ci"],
                        "fi": member["fi"],
                        "entry": {
                            "rule_key": rule_key,
                            "bucket": bucket,
                            "category": category,
                        },
                    })

    elif fname == "triage_decisions.json":
        # {"confirmed": ["ci:fi", ...]}
        for pair in data.get("confirmed", []):
            ci_s, fi_s = pair.split(":")
            refs.append({"ci": int(ci_s), "fi": int(fi_s), "entry": {"pair": pair}})

    return refs


def main():
    corpus = load_compact_corpus()
    lookup = build_ci_fi_lookup(corpus)

    backfilled = []
    missing = []
    for fname, decision_source in DECISION_FILES:
        path = BASE / fname
        if not path.exists():
            print(f"skip (not found): {fname}")
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        refs = extract_ci_fi_refs(fname, data)
        for ref in refs:
            key = (ref["ci"], ref["fi"])
            stable = lookup.get(key)
            if stable is None:
                missing.append({"source_file": fname, **ref})
                continue
            backfilled.append({
                "source_file": fname,
                "decision_source": decision_source,
                "ci": ref["ci"],
                "fi": ref["fi"],
                **stable,
                "original_entry": ref["entry"],
            })
        print(f"{fname}: {len(refs)} refs -> {len(refs) - sum(1 for m in missing if m['source_file']==fname)} resolved")

    out_path = BASE / "stable_keys_backfill.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"backfilled": backfilled, "missing": missing}, f, indent=2)

    print(f"\nTotal backfilled: {len(backfilled)}")
    print(f"Total missing (ci,fi not found in compact corpus): {len(missing)}")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
