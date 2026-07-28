"""Resolve the 3,614 clusters that Step 3's full-volume clustering formed
but that were never given a category decision (found during Step 6 held-out
validation — see STATE.md/ontology_debt.md for the finding: only 88 of 3,702
clusters matched the ORIGINAL 767-job corpus's exact rule::key strings, so
~254K clustered fields had no recorded answer at all).

Same auto-match discipline as residue_triage.py's original pattern: build a
reference set of (label/section text -> confirmed category) from every
already-confirmed decision (both the original cluster_decisions.json AND
every category assigned during Step 5's batch review), then fuzzy-match
each unresolved cluster's representative label against that reference.
High-confidence matches are auto-applied; everything else is flagged for
individual review, same as the original pipeline never let a weak match
through silently.

Run: python resolve_unresolved_clusters.py
Reads:  clusters_v2.json, cluster_decisions.json, oc_compact_full_v2.json,
        step5_batch*_decisions.json, step5_pattern_matched_decisions.json,
        taxonomy_v1.py (structural pattern names, for reject/special mapping)
Writes: unresolved_clusters_auto_matched.json (high-confidence, applied)
        unresolved_clusters_needs_review.json (low-confidence, for hand read)
"""

import glob
import json
import re
from collections import defaultdict

from taxonomy_v1 import TOPIC_CATEGORIES, STRUCTURAL_PATTERNS

_STOPWORDS = {
    "the", "a", "an", "is", "are", "you", "your", "to", "of", "for", "in",
    "on", "at", "and", "or", "if", "do", "does", "did", "please", "select",
    "any", "all", "that", "this", "with", "us", "our", "we", "will", "would",
    "can", "have", "has", "had", "s",
}


def normalize(s):
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"[*✱]", "", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def tokens(s):
    return {w for w in normalize(s).split() if w not in _STOPWORDS and len(w) > 2}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def main():
    with open("clusters_v2.json", encoding="utf-8") as f:
        clusters_data = json.load(f)
    with open("cluster_decisions.json", encoding="utf-8") as f:
        cd = json.load(f)
    with open("oc_compact_full_v2.json", encoding="utf-8") as f:
        compact = json.load(f)

    all_keys_in_decisions = set(cd["confirm"].keys()) | set(cd["reject"].keys()) | set(cd["special"].keys())

    # Build reference examples from the ORIGINAL confirmed clusters (against
    # the frozen oc_compact_full.json, so we need the original file's labels
    # too — but easier: just use the *category names* as reference tokens,
    # since we want to match unresolved clusters' label text against known
    # CATEGORY NAMES/taxonomy, not literally re-derive the original examples.
    # This mirrors residue_triage.py's spirit (match against confirmed
    # examples) but adapted to also use Step 5's decisions.
    category_examples = defaultdict(list)

    # From original cluster_decisions.json confirms: the key itself IS a
    # label/id-derived string, usable as an example.
    for rk, cat in cd["confirm"].items():
        _, key_text = rk.split("::", 1)
        toks = tokens(key_text)
        if len(toks) >= 2:
            category_examples[cat].append((key_text, toks))

    # From Step 5 batch decisions: reconstruct label text from the compact
    # corpus using (job_id, h) lookup.
    job_h_to_text = {}
    for c in compact:
        for f in c["fields"]:
            text = f.get("label") or f.get("section") or f.get("nearby") or ""
            job_h_to_text[(c["job_id"], f["h"])] = text

    for fname in glob.glob("step5_batch*_decisions.json"):
        with open(fname, encoding="utf-8") as f:
            entries = json.load(f)
        for e in entries:
            cat = e.get("category")
            if not cat:
                continue
            h = e.get("h")
            jid = e.get("job_id")
            text = job_h_to_text.get((jid, h), "")
            toks = tokens(text)
            if len(toks) >= 2:
                category_examples[cat].append((text, toks))

    # Dedup
    for cat in category_examples:
        seen = set()
        unique = []
        for lbl, toks in category_examples[cat]:
            key = frozenset(toks)
            if key not in seen:
                seen.add(key)
                unique.append((lbl, toks))
        category_examples[cat] = unique

    print(f"reference categories with examples: {len(category_examples)}")

    _MATCH_THRESHOLD = 0.6

    auto_matched = []
    needs_review = []

    for c in clusters_data["clusters"]:
        rk = f"{c['rule']}::{c['key']}"
        if rk in all_keys_in_decisions:
            continue  # already resolved

        m = c["members"][0]
        f = compact[m["ci"]]["fields"][m["fi"]]
        label_text = f.get("label") or f.get("section") or f.get("nearby") or c["key"]
        field_toks = tokens(label_text) or tokens(c["key"])

        best_cat = None
        best_score = 0.0
        if len(field_toks) >= 2:
            for cat, examples in category_examples.items():
                for ex_label, ex_toks in examples:
                    score = jaccard(field_toks, ex_toks)
                    if score > best_score:
                        best_score = score
                        best_cat = cat

        entry = {
            "rule_key": rk,
            "n_members": len(c["members"]),
            "sample_label": label_text,
            "sample_itype": f.get("itype"),
            "sample_section": f.get("section"),
            "suggested_category": best_cat,
            "match_score": round(best_score, 2),
        }

        if best_cat and best_score >= _MATCH_THRESHOLD:
            auto_matched.append(entry)
        else:
            needs_review.append(entry)

    auto_matched.sort(key=lambda x: -x["n_members"])
    needs_review.sort(key=lambda x: -x["n_members"])

    print(f"auto_matched: {len(auto_matched)} clusters, "
          f"{sum(e['n_members'] for e in auto_matched)} fields")
    print(f"needs_review: {len(needs_review)} clusters, "
          f"{sum(e['n_members'] for e in needs_review)} fields")

    with open("unresolved_clusters_auto_matched.json", "w", encoding="utf-8") as f:
        json.dump(auto_matched, f, indent=1, ensure_ascii=False)
    with open("unresolved_clusters_needs_review.json", "w", encoding="utf-8") as f:
        json.dump(needs_review, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
