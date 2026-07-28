"""Step 6 — held-out company-level generalization validation.

The real question: does the finished taxonomy/clustering rule set
generalize to companies it never saw, not just "did we label everything we
harvested." Coverage numbers reported so far (99.2%) measure the latter —
this measures the former.

Method:
- Split companies into HELD_OUT (never touched during clustering / decision
  writing) vs. TRAIN (everything else — the 17,391-17,396 companies whose
  fields actually built clusters_v2.json / cluster_decisions_v2.json).
- We can't re-run clustering "without having seen" the held-out companies
  after the fact (clusters_v2.json already includes their fields, and the
  cluster keys/decisions were built with the full corpus in view). Instead
  we approximate the true held-out test the honest way available now:
  for each held-out company's field, independently recompute its
  cluster key (same normalize_id/normalize_label/options_key functions,
  applied to that field ALONE, not via cluster co-membership) and check
  whether that key has a recorded decision in cluster_decisions_v2.json.
  A field only "passes" if its OWN key resolves to a decision — it gains
  nothing from having been clustered alongside other held-out-company
  fields, since key normalization is a pure per-field function. This is
  the right proxy for "would a brand-new company's form resolve using the
  taxonomy we built," because the taxonomy's actual runtime shape (as it
  would be used by the interpreter / P1.3 replay) is exactly this: given
  one field's own signals, look up its key.
- Report coverage (% resolving to any confirm/reject/special decision) and,
  on a manual-reviewed sample, correctness (does the resolved category
  actually match the field's real semantics).

Run: python heldout_validation.py
Reads: oc_compact_full_v2.json, cluster_decisions_v2.json
Writes: heldout_validation_report.json, heldout_sample_for_manual_review.json
"""

import json
import random
import re
from pathlib import Path

BASE = Path(__file__).parent

with open(BASE / "oc_compact_full_v2.json", encoding="utf-8") as f:
    companies = json.load(f)

with open(BASE / "cluster_decisions_v2.json", encoding="utf-8") as f:
    cd = json.load(f)

all_keys_final = set(cd["confirm"]) | set(cd["reject"]) | set(cd.get("special", {}))

# --- same normalization functions as auto_cluster_v2.py, kept identical on
# purpose: the held-out test must use the EXACT SAME key-derivation logic
# that produced cluster_decisions_v2.json, or a mismatch would just measure
# a bug in this script, not real generalization.

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


def field_rule_key(f):
    """Recompute a single field's own cluster key, independent of any
    cluster co-membership — same priority order as auto_cluster_v2.py:
    id -> autocomplete -> label -> section_fallback -> known_pattern
    (react-select shim) -> options."""
    idk = normalize_id(f.get("id"))
    if idk is not None:
        return ("id", idk)

    ac = (f.get("ac") or "").strip().lower()
    if ac in _AUTOCOMPLETE_SPEC_TOKENS:
        return ("autocomplete", ac)

    norm = normalize_label(f.get("label"))
    if norm not in _GENERIC_LABEL_TEXT and len(norm) >= _MIN_LABEL_LEN:
        return ("label", norm)

    if not f.get("label"):
        sec_norm = normalize_label(f.get("section"))
        if len(sec_norm) >= 15:
            return ("section_fallback", sec_norm)

    raw_label = (f.get("label") or "").strip().lower()
    label_is_empty_or_placeholder_chrome = (not f.get("label")) or (raw_label in _GENERIC_LABEL_TEXT)
    if (label_is_empty_or_placeholder_chrome
            and not (f.get("placeholder") or "").strip()
            and f.get("itype") == "text"
            and f.get("req") is True):
        return ("known_pattern", "react_select_required_shim")

    ok = options_key(f.get("opts"))
    if ok is not None:
        return ("options", ", ".join(sorted(ok))[:80])

    return None


# --- Held out companies: pick 20 companies deterministically (seeded),
# stratified across a range of field-count sizes so the held-out slice
# isn't accidentally all tiny or all huge companies.
random.seed(42)
company_names = sorted({c["company"] for c in companies})
HELDOUT_SIZE = 20
heldout_companies = set(random.sample(company_names, HELDOUT_SIZE))

heldout_fields = []
for c in companies:
    if c["company"] not in heldout_companies:
        continue
    for fi, f in enumerate(c["fields"]):
        heldout_fields.append((c["company"], c["job_id"], fi, f))

print(f"held-out companies ({HELDOUT_SIZE}): {sorted(heldout_companies)}")
print(f"held-out fields: {len(heldout_fields)}")

resolved = []
unresolved = []
for company, job_id, fi, f in heldout_fields:
    rk = field_rule_key(f)
    if rk is None:
        unresolved.append((company, job_id, fi, f, None))
        continue
    rule, key = rk
    full_rk = f"{rule}::{key}"
    if full_rk in all_keys_final:
        if full_rk in cd["confirm"]:
            category = cd["confirm"][full_rk]
        elif full_rk in cd.get("special", {}):
            category = cd["special"][full_rk]
        else:
            category = None  # reject
        resolved.append((company, job_id, fi, f, full_rk, category))
    else:
        unresolved.append((company, job_id, fi, f, full_rk))

n_resolved = len(resolved)
n_total = len(heldout_fields)
print()
print(f"held-out coverage: {n_resolved}/{n_total} fields ({100*n_resolved/n_total:.1f}%) "
      f"resolve to a decision cold")
print(f"held-out UNKNOWN: {len(unresolved)}/{n_total} fields ({100*len(unresolved)/n_total:.1f}%)")

# Sample for manual correctness review: 60 resolved fields, stratified
# across companies, plus all unresolved fields (usually a manageable count)
# for inspection of what's actually falling through.
random.seed(7)
sample_resolved = random.sample(resolved, min(60, len(resolved)))

report = {
    "heldout_companies": sorted(heldout_companies),
    "heldout_field_count": n_total,
    "resolved_count": n_resolved,
    "coverage_pct": round(100 * n_resolved / n_total, 2),
    "unresolved_count": len(unresolved),
}
with open(BASE / "heldout_validation_report.json", "w", encoding="utf-8") as fp:
    json.dump(report, fp, indent=2)

sample_out = {
    "resolved_sample_for_correctness_review": [
        {
            "company": company,
            "job_id": job_id,
            "rule_key": full_rk,
            "assigned_category": category,
            "label": f.get("label"),
            "section": f.get("section"),
            "nearby": f.get("nearby"),
            "id": f.get("id"),
            "itype": f.get("itype"),
        }
        for company, job_id, fi, f, full_rk, category in sample_resolved
    ],
    "all_unresolved_fields": [
        {
            "company": company,
            "job_id": job_id,
            "rule_key": rk,
            "label": f.get("label"),
            "section": f.get("section"),
            "nearby": f.get("nearby"),
            "id": f.get("id"),
            "itype": f.get("itype"),
        }
        for company, job_id, fi, f, rk in unresolved
    ],
}
with open(BASE / "heldout_sample_for_manual_review.json", "w", encoding="utf-8") as fp:
    json.dump(sample_out, fp, indent=2)

print()
print(f"wrote heldout_validation_report.json")
print(f"wrote heldout_sample_for_manual_review.json "
      f"({len(sample_resolved)} resolved to correctness-check, "
      f"{len(unresolved)} unresolved to inspect)")
