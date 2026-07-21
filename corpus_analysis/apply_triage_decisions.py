"""Founder decision (this session): bulk-confirm ALL 51 residue "likely
match" entries from residue_triage.json — every one scored >=0.60 word
overlap against an already-confirmed category, and a spot-check of the
weakest-scoring entries near the threshold found no false positives.

Output: scratchpad/triage_decisions.json — {"confirmed": [ci:fi, ...]} —
consumed by the artifact to pre-mark these as confirmed instead of requiring
51 individual clicks through the UI.
"""

import json

with open("scratchpad/residue_triage.json", encoding="utf-8") as f:
    triage = json.load(f)

confirmed_keys = [f"{e['ci']}:{e['fi']}" for e in triage["auto_match"]]

with open("scratchpad/triage_decisions.json", "w", encoding="utf-8") as f:
    json.dump({"confirmed": confirmed_keys}, f, indent=2)

print(f"confirmed: {len(confirmed_keys)} residue auto-match fields")
