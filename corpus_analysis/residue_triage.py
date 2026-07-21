"""Split residue fields into two piles:

1. auto_match — the field's label/section text is a NEAR-EXACT variant of a
   label string already inside a CONFIRMED cluster (high word overlap, same
   core phrase) — mechanical, not a semantic/intent judgment call.
2. needs_review — everything else. Genuinely ambiguous, novel, or too
   different in wording to trust a mechanical match.

This is deliberately conservative: the threshold is high specifically so
"auto_match" never smuggles in a judgment call disguised as string matching.
Anything borderline defaults to needs_review — better to over-ask the
founder than to silently mis-merge two different questions.
"""

import json
import re
from collections import defaultdict

with open("scratchpad/clusters.json", encoding="utf-8") as f:
    cd = json.load(f)
with open("scratchpad/oc_compact_full.json", encoding="utf-8") as f:
    data = json.load(f)
with open("scratchpad/cluster_decisions.json", encoding="utf-8") as f:
    dec = json.load(f)

_STOPWORDS = {
    "the", "a", "an", "is", "are", "you", "your", "to", "of", "for", "in",
    "on", "at", "and", "or", "if", "do", "does", "did", "please", "select",
    "any", "all", "that", "this", "with", "us", "our", "we", "will", "would",
    "can", "have", "has", "had",
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


# Build reference: canonical category -> list of (label_text, token_set) from
# CONFIRMED clusters only. Skip categories built from very short/generic
# labels (e.g. "phone", "gender") since token-overlap on 1-word labels is
# unreliable — those need id/autocomplete-strength signal, not word overlap.
category_examples = defaultdict(list)
for c in cd["clusters"]:
    rk = c["rule"] + "::" + c["key"]
    if rk not in dec["confirm"]:
        continue
    canonical = dec["confirm"][rk]
    for m in c["members"]:
        f = data[m["ci"]]["fields"][m["fi"]]
        lbl = f.get("label") or f.get("section") or ""
        toks = tokens(lbl)
        if len(toks) >= 3:  # only trust multi-word labels for fuzzy matching
            category_examples[canonical].append((lbl, toks))

# Dedup examples per category (keep unique token-sets)
for cat in category_examples:
    seen = []
    unique = []
    for lbl, toks in category_examples[cat]:
        key = frozenset(toks)
        if key not in seen:
            seen.append(key)
            unique.append((lbl, toks))
    category_examples[cat] = unique

print(f"categories with fuzzy-matchable examples: {len(category_examples)}")
for cat, examples in sorted(category_examples.items()):
    print(f"  {cat}: {len(examples)} example(s)")

_MATCH_THRESHOLD = 0.6  # conservative — most-of-the-words-in-common, not just topical overlap

results = {"auto_match": [], "needs_review": []}

for r in cd["residue"]:
    f = data[r["ci"]]["fields"][r["fi"]]
    label_text = f.get("label") or f.get("section") or ""
    field_toks = tokens(label_text)

    best_cat = None
    best_score = 0.0
    if len(field_toks) >= 3:  # same guard — don't fuzzy-match near-empty/short text
        for cat, examples in category_examples.items():
            for ex_label, ex_toks in examples:
                score = jaccard(field_toks, ex_toks)
                if score > best_score:
                    best_score = score
                    best_cat = cat

    entry = {
        "company": r["company"], "job_id": r["job_id"], "ci": r["ci"], "fi": r["fi"],
        "label_text": label_text,
        "suggested_category": best_cat,
        "match_score": round(best_score, 2),
    }

    if best_cat and best_score >= _MATCH_THRESHOLD:
        results["auto_match"].append(entry)
    else:
        results["needs_review"].append(entry)

print()
print(f"auto_match: {len(results['auto_match'])}")
print(f"needs_review: {len(results['needs_review'])}")

with open("scratchpad/residue_triage.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

print()
print("sample auto_match entries:")
for e in results["auto_match"][:15]:
    print(f"  {e['match_score']:.2f}  {e['company']:25s}  {e['label_text'][:50]!r:52s} -> {e['suggested_category']}")
