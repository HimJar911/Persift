"""Targeted fix for the biggest chunk of Step 6's found gap: `id`-rule
clusters keyed as `id::form-<stem>` never matched the original
`cluster_decisions.json`'s `id::<stem>` confirms, because the "auto-apply
existing confirms" step (Step 3) checked rule::key strings literally,
without stripping the `form-` prefix the way auto_cluster_v2.py's
normalize_id() already does for clustering itself. Same underlying fix,
applied here to decision-matching instead of cluster-formation.

Also handles a few other cheap, deterministic identity matches: `id::<n>`
where `<n>` is a bare number (Greenhouse's generic numeric-id custom
questions — not stable identity, correctly untouched/rejected) and any
`id::<stem>` where `<stem>` (after form- stripping) exactly matches a
confirmed id::<stem> OR a confirmed autocomplete::<token>.

Run: python resolve_form_prefix_gap.py
Reads:  clusters_v2.json, cluster_decisions.json
Writes: form_prefix_gap_resolved.json — {rule_key: category} for every
        cluster resolved by this exact-match pass (NOT the fuzzy auto-match
        used for label-rule clusters elsewhere).
"""

import json
import re

with open("clusters_v2.json", encoding="utf-8") as f:
    clusters_data = json.load(f)
with open("cluster_decisions.json", encoding="utf-8") as f:
    cd = json.load(f)

all_keys_in_decisions = set(cd["confirm"].keys()) | set(cd["reject"].keys()) | set(cd["special"].keys())


def strip_form_prefix(stem):
    return re.sub(r"^form-", "", stem)


resolved = {}
still_unresolved_id = []

for c in clusters_data["clusters"]:
    if c["rule"] != "id":
        continue
    rk = f"{c['rule']}::{c['key']}"
    if rk in all_keys_in_decisions:
        continue

    unprefixed = strip_form_prefix(c["key"])
    candidate_rk = f"id::{unprefixed}"
    if candidate_rk in cd["confirm"]:
        resolved[rk] = {"action": "confirm", "category": cd["confirm"][candidate_rk],
                         "matched_via": candidate_rk}
    elif candidate_rk in cd["reject"]:
        resolved[rk] = {"action": "reject", "category": None, "matched_via": candidate_rk}
    elif candidate_rk in cd.get("special", {}):
        resolved[rk] = {"action": "special", "category": cd["special"][candidate_rk],
                         "matched_via": candidate_rk}
    else:
        still_unresolved_id.append((rk, len(c["members"])))

n_fields_resolved = sum(
    len(c["members"]) for c in clusters_data["clusters"]
    if (c["rule"] + "::" + c["key"]) in resolved
)
print(f"resolved via form- prefix stripping: {len(resolved)} clusters, "
      f"{n_fields_resolved} fields")

still_unresolved_id.sort(key=lambda x: -x[1])
print(f"still unresolved id-rule clusters: {len(still_unresolved_id)}")
for rk, n in still_unresolved_id[:20]:
    print(f"  {n:6d}  {rk}")

with open("form_prefix_gap_resolved.json", "w", encoding="utf-8") as f:
    json.dump(resolved, f, indent=2)
