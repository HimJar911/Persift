"""Apply all Step 6 gap-resolution decision files
(form_prefix_gap_resolved.json, id_rule_gap_decisions.json,
label_rule_gap_decisions_*.json) onto clusters_v2.json, producing one
merged decision map covering every cluster Step 3 formed.

Label-rule decisions are keyed by TRUNCATED label text (matching how the
clusters were read off a printed, truncated listing) — resolved by PREFIX
match against the real cluster key, deliberately, since many genuinely
distinct full label strings ("...for employment", "...for employment in
Germany", "...for employment in Canada", etc.) share one truncated prefix
and the SAME real category. Applying by prefix is correct here specifically
because every verified sample under a given prefix was confirmed to share
the same underlying question intent (see resolve_unresolved_clusters.py's
inline notes) — this is NOT the same risk as the department_interest
cross-company label-text collision (that was collapsing DIFFERENT
questions that happened to share exact words; this is one question with
minor wording variants sharing a common opening clause).

Run: python apply_gap_decisions.py
Reads:  clusters_v2.json, cluster_decisions.json, all gap decision files
Writes: cluster_decisions_v2.json — cluster_decisions.json's original
        confirm/reject/special buckets, PLUS every newly-resolved cluster
        merged in under the SAME rule::key scheme (now covering
        clusters_v2.json, not just the original 767-job clusters.json).
"""

import glob
import json

with open("clusters_v2.json", encoding="utf-8") as f:
    clusters_data = json.load(f)
with open("cluster_decisions.json", encoding="utf-8") as f:
    cd = json.load(f)

all_keys_in_decisions = set(cd["confirm"].keys()) | set(cd["reject"].keys()) | set(cd.get("special", {}).keys())

new_confirm = dict(cd["confirm"])
new_reject = dict(cd["reject"])
new_special = dict(cd.get("special", {}))

applied_count = 0
applied_fields = 0


def apply_decision(rk, decision):
    global applied_count, applied_fields
    action = decision["action"]
    cat = decision.get("category")
    if action == "confirm":
        new_confirm[rk] = cat
    elif action == "reject":
        new_reject[rk] = None
    elif action == "special":
        new_special[rk] = cat
    applied_count += 1


# 1. form_prefix_gap_resolved.json — exact rule::key already
with open("form_prefix_gap_resolved.json", encoding="utf-8") as f:
    form_prefix = json.load(f)
for rk, decision in form_prefix.items():
    if rk in all_keys_in_decisions:
        continue
    apply_decision(rk, decision)

# 2. id_rule_gap_decisions.json — exact rule::key already (id::<n>)
with open("id_rule_gap_decisions.json", encoding="utf-8") as f:
    id_gap = json.load(f)
for rk, decision in id_gap.items():
    if rk in all_keys_in_decisions:
        continue
    apply_decision(rk, decision)

# 2b. anduril_widget_gap_decisions*.json — exact rule::key already (label::<full key>)
for fname in ["anduril_widget_gap_decisions.json", "anduril_widget_gap_decisions_2.json"]:
    with open(fname, encoding="utf-8") as f:
        anduril_gap = json.load(f)
    for rk, decision in anduril_gap.items():
        if rk in all_keys_in_decisions:
            continue
        apply_decision(rk, decision)

# 2c. coupang_english_gap_decisions.json — exact rule::key already
with open("coupang_english_gap_decisions.json", encoding="utf-8") as f:
    coupang_gap = json.load(f)
for rk, decision in coupang_gap.items():
    if rk in all_keys_in_decisions:
        continue
    apply_decision(rk, decision)

# 2d. non_english gap exclusion files — mark as reject with a note, so they
# count as "resolved" (deliberately excluded) rather than showing up as an
# open gap in coverage reporting.
for fname in ["non_english_label_gap_exclusions.json", "non_english_gap_exclusions_2.json", "non_english_gap_exclusions_3.json", "non_english_gap_exclusions_4.json", "non_english_gap_exclusions_korean.json", "non_english_gap_exclusions_5.json", "non_english_gap_exclusions_6.json", "non_english_gap_exclusions_7.json"]:
    with open(fname, encoding="utf-8") as f:
        non_english_gap = json.load(f)
    for rk in non_english_gap:
        if rk in all_keys_in_decisions:
            continue
        apply_decision(rk, {"action": "reject", "category": None})

# 3. label_rule_gap_decisions_*.json — PREFIX match against real cluster
# keys, for whichever rule the entry's prefix indicates (label::,
# section_fallback::, or options::). Exact-match rules (id::) never appear
# in these files.
keys_by_rule = {}
for c in clusters_data["clusters"]:
    keys_by_rule.setdefault(c["rule"], set()).add(c["key"])

label_decision_files = sorted(glob.glob("label_rule_gap_decisions_*.json"))
for fname in label_decision_files:
    with open(fname, encoding="utf-8") as f:
        label_gap = json.load(f)
    for rk_truncated, decision in label_gap.items():
        rule, truncated_key = rk_truncated.split("::", 1)
        truncated_key = truncated_key[:-2] if truncated_key.endswith("_2") else truncated_key
        candidate_keys = keys_by_rule.get(rule, set())
        matches = [k for k in candidate_keys if k.startswith(truncated_key)]
        for full_key in matches:
            full_rk = f"{rule}::{full_key}"
            if full_rk in all_keys_in_decisions:
                continue
            apply_decision(full_rk, decision)

print(f"applied {applied_count} new rule::key decisions")

final = {
    "confirm": new_confirm,
    "reject": new_reject,
    "special": new_special,
    "unresolved": cd.get("unresolved", []),
    "not_found": cd.get("not_found", []),
}

with open("cluster_decisions_v2.json", "w", encoding="utf-8") as f:
    json.dump(final, f, indent=2)

# Report final coverage
all_keys_final = set(final["confirm"]) | set(final["reject"]) | set(final["special"])
total_clusters = len(clusters_data["clusters"])
resolved_clusters = sum(1 for c in clusters_data["clusters"] if f"{c['rule']}::{c['key']}" in all_keys_final)
total_fields = sum(len(c["members"]) for c in clusters_data["clusters"])
resolved_fields = sum(len(c["members"]) for c in clusters_data["clusters"] if f"{c['rule']}::{c['key']}" in all_keys_final)
print(f"final coverage: {resolved_clusters}/{total_clusters} clusters, "
      f"{resolved_fields}/{total_fields} fields ({100*resolved_fields/total_fields:.1f}%)")
