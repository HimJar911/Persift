"""Re-run of auto_cluster.py's deterministic clustering, at full volume
(oc_compact_full_v2.json — 17,423 companies / ~633K fields, vs. the
original's 116 companies / 3,074 fields).

Identical clustering rules to auto_cluster.py (same priority order: id ->
autocomplete -> label -> section_fallback -> known_pattern/react-select-shim
-> options) — this is a separate file (not an edit to the original) so the
original stays a working reference for the 767-job pass, and this one's
output is explicitly versioned (clusters_v2.json) rather than overwriting
clusters.json, which corpus_analysis/README.md's decision files still key
against via the original (ci, fi) scheme.

Run: python corpus_analysis/auto_cluster_v2.py
Reads:  corpus_analysis/oc_compact_full_v2.json
Writes: corpus_analysis/clusters_v2.json
"""

import json
import re
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).parent

with open(BASE / "oc_compact_full_v2.json", encoding="utf-8") as f:
    companies = json.load(f)

_AUTOCOMPLETE_SPEC_TOKENS = {
    "given-name", "additional-name", "family-name", "name", "nickname",
    "email", "tel", "tel-national", "tel-country-code", "tel-area-code",
    "tel-local", "street-address", "address-line1", "address-line2",
    "address-level1", "address-level2", "postal-code", "country",
    "country-name", "bday", "bday-day", "bday-month", "bday-year",
    "sex", "organization", "organization-title", "url", "photo",
    "language",
}

_MIN_LABEL_LEN = 4

_GENERIC_ID_STEMS = {
    "question", "input", "chkbox-id", "rc_select", "custom-field", "typehead",
}

# Generic widget placeholder/chrome text that some label-extraction
# strategies (confirmed: "preceding-text") mistakenly capture as if it were
# a real question label. Found during the full-volume re-run: a
# react-select required-input shim (FORM_ENGINE_DESIGN.md §7) normally has
# label=="" and gets caught by the known_pattern rule below — but when
# label_strategy=="preceding-text" grabs the widget's own "Select..."
# placeholder text, label is no longer empty, so the shim rule's `not
# f.get("label")` guard fails to fire and the field falls through into the
# generic label-match rule instead, false-merging 106,946 fields (all one
# single field_id_hash, "8e474141" — 100% mechanically identical) across
# hundreds of companies under a fake "select" question, the same
# generic-label-false-merge shape as the department_interest/
# location_preference correction already documented in
# corpus_analysis/README.md. Excluded here so the label rule never sees it,
# so the shim rule below (or a real cluster) can classify the underlying
# field on its own field-level signals instead.
# Localized variants confirmed via the same field_id_hash (8e474141) as the
# English "Select..." shim — Korean, Japanese (two rendering variants seen:
# half-width and full-width ellipsis).
_GENERIC_LABEL_TEXT = {"select", "select...", "선택...", "選択...", "選擇......"}

_GENERIC_OPTION_SETS = {
    frozenset(x.lower() for x in ["yes", "no"]),
    frozenset(x.lower() for x in ["yes", "no", ""]),
    frozenset(x.lower() for x in ["y", "n"]),
    frozenset(x.lower() for x in ["true", "false"]),
    frozenset(x.lower() for x in ["select...", "yes", "no"]),
}


def normalize_id(field_id):
    if not field_id:
        return None
    stem = re.sub(r"[-_]{1,2}\d+$", "", field_id.strip().lower())
    # Greenhouse prefixes some field ids with "form-" (e.g.
    # "form-question_<jobid>", "form-resume") — strip it before checking
    # against the generic-stem denylist so "form-question" is recognized as
    # the same generic custom-question wrapper as bare "question" (found
    # during the full-volume re-run: id::form-question false-merged 709
    # distinct real questions — background-check consent, RN/LPN licensure,
    # age requirement, BAYADA employment history, etc. — into one fake
    # 5,516-field cluster, the same false-merge shape as
    # department_interest/location_preference, just via the id rule).
    # "form-resume" stays real (verified: always literally "Resume/CV" or
    # its required/localized variant across all 2,077 members) since
    # "resume" isn't in the generic-stem denylist.
    unprefixed = re.sub(r"^form-", "", stem)
    if not stem or stem in _GENERIC_ID_STEMS or unprefixed in _GENERIC_ID_STEMS:
        return None
    return stem


def normalize_label(label):
    if not label:
        return ""
    s = label.lower()
    s = re.sub(r"[*✱]", "", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def options_key(opts):
    if not opts or not isinstance(opts, list) or len(opts) < 3:
        return None
    norm = frozenset(str(o).strip().lower() for o in opts if str(o).strip())
    if len(norm) < 3:
        return None
    if norm in _GENERIC_OPTION_SETS:
        return None
    return norm


all_fields = []
for ci, c in enumerate(companies):
    for fi, f in enumerate(c["fields"]):
        all_fields.append((c["company"], c["job_id"], ci, fi, f))

print(f"total fields: {len(all_fields)}")

assigned = set()
clusters = []

by_id = defaultdict(list)
for company, job_id, ci, fi, f in all_fields:
    key = normalize_id(f.get("id"))
    if key is not None:
        by_id[key].append((company, job_id, ci, fi, f))
for key, members in by_id.items():
    if len(members) < 2:
        continue
    clusters.append({"rule": "id", "key": key, "members": members})
    for company, job_id, ci, fi, f in members:
        assigned.add((ci, fi))

by_autocomplete = defaultdict(list)
for company, job_id, ci, fi, f in all_fields:
    if (ci, fi) in assigned:
        continue
    ac = (f.get("ac") or "").strip().lower()
    if ac in _AUTOCOMPLETE_SPEC_TOKENS:
        by_autocomplete[ac].append((company, job_id, ci, fi, f))
for ac, members in by_autocomplete.items():
    if len(members) < 2:
        continue
    clusters.append({"rule": "autocomplete", "key": ac, "members": members})
    for company, job_id, ci, fi, f in members:
        assigned.add((ci, fi))

by_label = defaultdict(list)
for company, job_id, ci, fi, f in all_fields:
    if (ci, fi) in assigned:
        continue
    norm = normalize_label(f.get("label"))
    if norm in _GENERIC_LABEL_TEXT:
        continue
    if len(norm) >= _MIN_LABEL_LEN:
        by_label[norm].append((company, job_id, ci, fi, f))
for norm, members in by_label.items():
    if len(members) < 2:
        continue
    clusters.append({"rule": "label", "key": norm, "members": members})
    for company, job_id, ci, fi, f in members:
        assigned.add((ci, fi))

_MIN_SECTION_FALLBACK_LEN = 15
by_section_fallback = defaultdict(list)
for company, job_id, ci, fi, f in all_fields:
    if (ci, fi) in assigned:
        continue
    if f.get("label"):
        continue
    norm = normalize_label(f.get("section"))
    if len(norm) >= _MIN_SECTION_FALLBACK_LEN:
        by_section_fallback[norm].append((company, job_id, ci, fi, f))
for norm, members in by_section_fallback.items():
    if len(members) < 2:
        continue
    clusters.append({"rule": "section_fallback", "key": norm, "members": members})
    for company, job_id, ci, fi, f in members:
        assigned.add((ci, fi))

by_react_select_shim = defaultdict(list)
for company, job_id, ci, fi, f in all_fields:
    if (ci, fi) in assigned:
        continue
    # Compare the RAW (lowercased, stripped) label against the generic-text
    # set, not normalize_label()'s output — normalize_label strips all
    # non-ASCII chars, so the localized "Select..." variants (Korean
    # 선택..., Japanese 選択.../選擇......) collapse to "" and would never
    # match here if compared post-normalization. Confirmed via raw HTML
    # (see FORM_ENGINE_DESIGN.md §7 + this session's finding): label is
    # either truly empty, OR populated with the widget's own "Select..."
    # placeholder text (in any of the locales seen) by the preceding-text
    # label strategy — both are the same non-interactive required-input
    # shim, not two different fields.
    raw_label = (f.get("label") or "").strip().lower()
    label_is_empty_or_placeholder_chrome = (not f.get("label")) or (raw_label in _GENERIC_LABEL_TEXT)
    # The original rule also required section in ("", "phone") — too
    # narrow at full volume: the SAME field_id_hash (8e474141, i.e. the
    # exact same DOM shim by the harvester's own identity definition)
    # showed up with section values that are just localized "Phone"
    # translations (Telefon/전화/電話/Teléfono/Téléphone/Telefoon/电话/
    # Puhelin) or demographic-survey section names never seen in the
    # 116-company seed sample (e.g. "USA - Self-Identification Survey",
    # "UK - Demographic Questionnaire"). Since the hash already guarantees
    # DOM-structural identity, the section check added no real
    # discrimination here and only caused false residue — dropped rather
    # than grown into an ever-expanding locale denylist.
    if (label_is_empty_or_placeholder_chrome
            and not (f.get("placeholder") or "").strip()
            and f.get("itype") == "text"
            and f.get("req") is True):
        by_react_select_shim["react_select_required_shim"].append((company, job_id, ci, fi, f))
for key, members in by_react_select_shim.items():
    if len(members) < 2:
        continue
    clusters.append({"rule": "known_pattern", "key": key, "members": members})
    for company, job_id, ci, fi, f in members:
        assigned.add((ci, fi))

by_options = defaultdict(list)
for company, job_id, ci, fi, f in all_fields:
    if (ci, fi) in assigned:
        continue
    key = options_key(f.get("opts"))
    if key is not None:
        by_options[key].append((company, job_id, ci, fi, f))
for key, members in by_options.items():
    if len(members) < 2:
        continue
    clusters.append({"rule": "options", "key": ", ".join(sorted(key))[:80], "members": members})
    for company, job_id, ci, fi, f in members:
        assigned.add((ci, fi))

total_clustered = sum(len(c["members"]) for c in clusters)
residue = len(all_fields) - total_clustered

print(f"clusters formed: {len(clusters)}")
print(f"fields auto-clustered: {total_clustered}")
print(f"residue (manual review needed): {residue}")
print()
print("by rule:")
for rule in ["id", "autocomplete", "label", "section_fallback", "known_pattern", "options"]:
    rc = [c for c in clusters if c["rule"] == rule]
    rf = sum(len(c["members"]) for c in rc)
    print(f"  {rule}: {len(rc)} clusters, {rf} fields")

print()
print("largest clusters:")
for c in sorted(clusters, key=lambda x: -len(x["members"]))[:30]:
    print(f"  [{c['rule']}] {c['key']!r}: {len(c['members'])} fields")

out_clusters = []
for idx, c in enumerate(clusters):
    out_clusters.append({
        "cluster_id": idx,
        "rule": c["rule"],
        "key": c["key"],
        "members": [
            {"company": company, "job_id": job_id, "ci": ci, "fi": fi}
            for company, job_id, ci, fi, f in c["members"]
        ],
    })

out_residue = []
for company, job_id, ci, fi, f in all_fields:
    if (ci, fi) not in assigned:
        out_residue.append({"company": company, "job_id": job_id, "ci": ci, "fi": fi})

with open(BASE / "clusters_v2.json", "w", encoding="utf-8") as f:
    json.dump({"clusters": out_clusters, "residue": out_residue}, f)

print()
print(f"written corpus_analysis/clusters_v2.json — {len(out_clusters)} clusters, {len(out_residue)} residue fields")
