"""Deterministic pre-clustering for the P1 open-coding pass.

Three rules, in priority order, each field placed in exactly one cluster
(or left unclustered = manual residue):

1. autocomplete spec match — only real HTML-spec tokens (not "off"/""),
   grouped by exact autocomplete value.
2. exact/near-exact normalized label match — only when the normalized
   label is "specific enough" (length threshold), to avoid collapsing
   generic one-word labels that could mean different things per form.
3. identical non-trivial options list match — full option array must be
   identical and not a trivially generic short list (e.g. yes/no).

No LLM involved. No semantic guessing about what a label "means" beyond
what the HTML autocomplete spec already defines. Every cluster records
which rule produced it and why, so it's auditable.
"""

import json
import re
from collections import defaultdict

with open("scratchpad/oc_compact_full.json", encoding="utf-8") as f:
    companies = json.load(f)

# Recognized HTML autocomplete spec tokens worth trusting as identity.
# "off"/"on"/"" are NOT identity signals — they say nothing about field meaning.
_AUTOCOMPLETE_SPEC_TOKENS = {
    "given-name", "additional-name", "family-name", "name", "nickname",
    "email", "tel", "tel-national", "tel-country-code", "tel-area-code",
    "tel-local", "street-address", "address-line1", "address-line2",
    "address-level1", "address-level2", "postal-code", "country",
    "country-name", "bday", "bday-day", "bday-month", "bday-year",
    "sex", "organization", "organization-title", "url", "photo",
    "language",
}

_MIN_LABEL_LEN = 4  # normalized chars; below this, too generic to trust alone (lowered from 8 — id-rule now catches short generic labels like "phone"/"country" via a stronger signal, so this threshold only needs to guard truly bare single letters/noise)

# id attribute is too generic/auto-generated to trust as identity on its own.
_GENERIC_ID_STEMS = {
    "question",       # Greenhouse's generic custom-question wrapper id (question_<jobid>) — no semantic meaning
    "input",          # generic
    "chkbox-id",      # generic checkbox wrapper, seen across unrelated cookie/consent widgets
    "rc_select",      # generic react-select internal id
    "custom-field",   # generic
    "typehead",       # generic typeahead widget internal id
}
# NOTE: g-recaptcha-response-100000 has a numeric suffix that looks like an
# index (matches the "-\d+$" strip pattern) but is actually a stable widget
# id shared across pages, not a per-instance counter — it's a real, useful
# match once normalized, so it's deliberately NOT excluded here.

# Options lists this short/generic don't prove sameness on their own.
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
    # strip trailing index suffixes like "--0", "-2", "_1"
    stem = re.sub(r"[-_]{1,2}\d+$", "", field_id.strip().lower())
    if not stem or stem in _GENERIC_ID_STEMS:
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


# Flatten to (company, field_index, field) tuples
all_fields = []
for ci, c in enumerate(companies):
    for fi, f in enumerate(c["fields"]):
        all_fields.append((c["company"], c["job_id"], ci, fi, f))

print(f"total fields: {len(all_fields)}")

assigned = set()  # (ci, fi) already placed in a cluster
clusters = []  # list of dicts: {rule, key, members: [...]}

# --- Rule 0: stable id attribute match (highest confidence — devs pick
# semantic ids like "first_name"/"resume"/"gender" even when the visible
# label is generic/short; strip auto-generated index suffixes first) ---
by_id = defaultdict(list)
for company, job_id, ci, fi, f in all_fields:
    key = normalize_id(f.get("id"))
    if key is not None:
        by_id[key].append((company, job_id, ci, fi, f))

for key, members in by_id.items():
    if len(members) < 2:
        continue
    clusters.append({
        "rule": "id",
        "key": key,
        "members": members,
    })
    for company, job_id, ci, fi, f in members:
        assigned.add((ci, fi))

# --- Rule 1: autocomplete spec match (only unassigned fields) ---
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
    clusters.append({
        "rule": "autocomplete",
        "key": ac,
        "members": members,
    })
    for company, job_id, ci, fi, f in members:
        assigned.add((ci, fi))

# --- Rule 2: normalized label match (only unassigned fields) ---
by_label = defaultdict(list)
for company, job_id, ci, fi, f in all_fields:
    if (ci, fi) in assigned:
        continue
    norm = normalize_label(f.get("label"))
    if len(norm) >= _MIN_LABEL_LEN:
        by_label[norm].append((company, job_id, ci, fi, f))

for norm, members in by_label.items():
    if len(members) < 2:
        continue
    clusters.append({
        "rule": "label",
        "key": norm,
        "members": members,
    })
    for company, job_id, ci, fi, f in members:
        assigned.add((ci, fi))

# --- Rule 2b: section-as-fallback-label match (only unassigned fields with
# NO label at all). Some ATS forms put the real question text in `section`
# (nearest heading/container text) rather than a proper <label> — e.g. a
# checkbox_group whose section IS the question ("Please indicate which
# locations you are able work in..."). Founder-caught gap: these were
# silently counted as "no label found" and dropped into residue even though
# the real question text was sitting right there in a different field. Only
# applies when label is EMPTY (never overrides a real label) and section is
# long enough to plausibly be a real question, not a one-word heading. ---
_MIN_SECTION_FALLBACK_LEN = 15  # normalized chars — shorter section text is more likely a generic heading ("Phone", "Details") than a real question
by_section_fallback = defaultdict(list)
for company, job_id, ci, fi, f in all_fields:
    if (ci, fi) in assigned:
        continue
    if f.get("label"):
        continue  # only fires when there is truly no label
    norm = normalize_label(f.get("section"))
    if len(norm) >= _MIN_SECTION_FALLBACK_LEN:
        by_section_fallback[norm].append((company, job_id, ci, fi, f))

for norm, members in by_section_fallback.items():
    if len(members) < 2:
        continue
    clusters.append({
        "rule": "section_fallback",
        "key": norm,
        "members": members,
    })
    for company, job_id, ci, fi, f in members:
        assigned.add((ci, fi))

# --- Rule 2c: react-select hidden required-shim (confirmed via raw HTML,
# not a heuristic guess — see FORM_ENGINE_DESIGN.md §7). A library-injected
# empty, required, non-interactive input trailing a custom combobox, used
# solely to let native HTML5 `required` validation fire on that combobox.
# Signature confirmed by hand against corpus/pages/*.html.gz (617mediagroup,
# job 6917269002): a single page had SIX `remix-css-*-requiredInput` shim
# occurrences — one per custom combobox on the page (country, location,
# discipline, school, degree), not just the phone/country one originally
# found. Broadened accordingly: tag=input, itype=text, label empty,
# required=true, AND (section empty OR section=="Phone" — the only two
# section values observed across confirmed instances). The compact field
# JSON doesn't carry tabindex/aria-hidden/class, so this rule is narrower
# than the full DOM signature — it only fires on the exact observed
# combination, not a bare "empty+required" guess, to avoid false-positiving
# on some other required-but-real field with a genuinely different section. ---
by_react_select_shim = defaultdict(list)
for company, job_id, ci, fi, f in all_fields:
    if (ci, fi) in assigned:
        continue
    sec = (f.get("section") or "").strip().lower()
    if (not f.get("label")
            and sec in ("", "phone")
            and not (f.get("placeholder") or "").strip()
            and f.get("itype") == "text"
            and f.get("req") is True):
        by_react_select_shim["react_select_required_shim"].append((company, job_id, ci, fi, f))

for key, members in by_react_select_shim.items():
    if len(members) < 2:
        continue
    clusters.append({
        "rule": "known_pattern",
        "key": key,
        "members": members,
    })
    for company, job_id, ci, fi, f in members:
        assigned.add((ci, fi))

# --- Rule 3: identical non-trivial options list (only unassigned fields) ---
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
    clusters.append({
        "rule": "options",
        "key": ", ".join(sorted(key))[:80],
        "members": members,
    })
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
for c in sorted(clusters, key=lambda x: -len(x["members"]))[:20]:
    print(f"  [{c['rule']}] {c['key']!r}: {len(c['members'])} fields")

# --- Build output structures ---

# Clusters, serializable
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

# Residue: individual field pointers not in any cluster
out_residue = []
for company, job_id, ci, fi, f in all_fields:
    if (ci, fi) not in assigned:
        out_residue.append({"company": company, "job_id": job_id, "ci": ci, "fi": fi})

with open("scratchpad/clusters.json", "w", encoding="utf-8") as f:
    json.dump({"clusters": out_clusters, "residue": out_residue}, f)

print()
print(f"written scratchpad/clusters.json — {len(out_clusters)} clusters, {len(out_residue)} residue fields")
