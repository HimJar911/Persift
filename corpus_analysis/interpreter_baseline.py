"""P1.3 baseline interpreter — the first `interpret(field) -> dict` the
replay harness (`replay.py`) scores against.

Not a new design: this is `auto_cluster_v2.py`'s deterministic key-derivation
logic (id -> autocomplete -> label -> section_fallback -> known_pattern ->
options, in that priority order) ported from "cluster a whole corpus" into
"classify one field," so it's callable per-field the way a real interpreter
must be (FORM_ENGINE_DESIGN.md §3.2: "Interpretation is a pure function over
the serialized Field"). The normalize_* functions and denylists are kept
byte-identical to auto_cluster_v2.py on purpose — they're what produced
cluster_decisions_v2.json, so scoring against a diverged copy would just
measure a bug in this port, not real interpreter quality (same requirement
heldout_validation.py's docstring calls out for itself).

This baseline is deliberately dumb: pure rule-lookup, no multi-signal
weighting, no partial-agreement confidence. P1.4 is where real interpretation
gets designed (autocomplete > name/id > label > placeholder > nearby-text
tiers, new categories like consent_background_check/essay). The baseline
exists only so replay.py has *something* to produce a first number against —
"here's what plain rule-lookup already gets," which is also the number P1.4
needs to beat.
"""

import json
import re
from pathlib import Path

BASE = Path(__file__).parent

with open(BASE / "cluster_decisions_v2.json", encoding="utf-8") as f:
    _CD = json.load(f)

_CONFIRM = _CD["confirm"]
_REJECT = _CD["reject"]
_SPECIAL = _CD["special"]

# auto_cluster_v2.py only forms a cluster for a given (rule, key) if >= 2
# fields share it (`if len(members) < 2: continue`) — a field whose derived
# key is unique to itself never became a cluster, so that key never got a
# decision written for it, and the field falls through to try the NEXT
# rule instead (this mirrors the clustering pass's own "already assigned"
# semantics, which only marks a field assigned once it joins a real
# multi-member cluster). A further ~50 keys were added on top of
# clusters_v2.json's own clusters by later gap-decision passes
# (apply_gap_decisions.py's Step 6 files) without necessarily forming a
# clusters_v2.json entry — so the true "does this key resolve" set is
# cluster_decisions_v2.json's own key space, not clusters_v2.json's,
# loaded here so candidate_keys() can check "would this key actually
# resolve" before treating a rule as matched and stopping.
_VALID_CLUSTER_KEYS = set()
for _rk in list(_CONFIRM) + list(_REJECT) + list(_SPECIAL):
    _rule, _key = _rk.split("::", 1)
    _VALID_CLUSTER_KEYS.add((_rule, _key))

# --- identical to auto_cluster_v2.py — do not let these drift independently.

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

_MIN_SECTION_FALLBACK_LEN = 15


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


def _is_react_select_shim(field):
    raw_label = (field.get("label") or "").strip().lower()
    label_is_empty_or_placeholder_chrome = (
        (not field.get("label")) or (raw_label in _GENERIC_LABEL_TEXT)
    )
    return (
        label_is_empty_or_placeholder_chrome
        and not (field.get("placeholder") or "").strip()
        and field.get("itype") == "text"
        and field.get("req") is True
    )


def candidate_keys(field):
    """Yield (rule, key) pairs for `field`, in the same priority order
    auto_cluster_v2.py applies, but ONLY yield a rule's key if that (rule,
    key) pair actually formed a real cluster (>= 2 fields sharing it,
    per _VALID_CLUSTER_KEYS) — otherwise fall through to the next rule,
    exactly mirroring auto_cluster_v2.py's own behavior (a field with a
    globally-unique id never becomes an "id" cluster, so it must still be
    eligible to cluster on label/section_fallback/etc.). Stopping at the
    first NON-None key regardless of cluster membership was an earlier,
    incorrect version of this function — it under-resolved by ~3,500
    fields relative to the real pipeline's cluster_decisions_v2.json,
    caught during P1.3's own verification pass (replay's reported
    coverage came in under the known 99.2% baseline, which is exactly the
    kind of divergence FORM_ENGINE_DESIGN.md's replay design is meant to
    catch — in this case a bug in the port, not a real finding).
    """
    id_key = normalize_id(field.get("id"))
    if id_key is not None and ("id", id_key) in _VALID_CLUSTER_KEYS:
        yield ("id", id_key)
        return

    ac = (field.get("ac") or "").strip().lower()
    if ac in _AUTOCOMPLETE_SPEC_TOKENS and ("autocomplete", ac) in _VALID_CLUSTER_KEYS:
        yield ("autocomplete", ac)
        return

    label_norm = normalize_label(field.get("label"))
    if (label_norm and label_norm not in _GENERIC_LABEL_TEXT and len(label_norm) >= _MIN_LABEL_LEN
            and ("label", label_norm) in _VALID_CLUSTER_KEYS):
        yield ("label", label_norm)
        return

    if not field.get("label"):
        section_norm = normalize_label(field.get("section"))
        if len(section_norm) >= _MIN_SECTION_FALLBACK_LEN and ("section_fallback", section_norm) in _VALID_CLUSTER_KEYS:
            yield ("section_fallback", section_norm)
            return

    if _is_react_select_shim(field) and ("known_pattern", "react_select_required_shim") in _VALID_CLUSTER_KEYS:
        yield ("known_pattern", "react_select_required_shim")
        return

    opts_key = options_key(field.get("opts"))
    if opts_key is not None:
        opts_str = ", ".join(sorted(opts_key))[:80]
        if ("options", opts_str) in _VALID_CLUSTER_KEYS:
            yield ("options", opts_str)
            return


def ground_truth_lookup(field):
    """The answer-key side: does this field's own key resolve to a recorded
    decision in cluster_decisions_v2.json? Kept as its own function, separate
    from interpret() below, even though today it calls the identical
    candidate_keys()/normalize_* code the baseline interpreter uses.

    That coincidence is only true because the baseline interpreter currently
    *is* the key-derivation logic that built the answer key. It won't stay
    true once P1.4 introduces real multi-signal interpretation — a future
    change to key-derivation (e.g. a smarter normalize_label) must be
    distinguishable in replay's report from a silent redefinition of ground
    truth itself. Two functions that happen to agree today keeps that
    distinction possible later at zero cost now.

    Returns {"category": str, "bucket": "confirm"|"reject"|"special",
    "rule": str, "key": str} or {"category": None, "bucket": None,
    "rule": None, "key": None} if no rule-derived key resolves.
    """
    for rule, key in candidate_keys(field):
        full_key = f"{rule}::{key}"
        if full_key in _CONFIRM:
            return {"category": _CONFIRM[full_key], "bucket": "confirm", "rule": rule, "key": full_key}
        if full_key in _REJECT:
            return {"category": None, "bucket": "reject", "rule": rule, "key": full_key}
        if full_key in _SPECIAL:
            return {
                "category": _SPECIAL[full_key]["kind"],
                "bucket": "special",
                "rule": rule,
                "key": full_key,
            }
    return {"category": None, "bucket": None, "rule": None, "key": None}


def interpret(field):
    """field: one compact-schema record (see build_compact_corpus_v2.py's
    to_compact_field — h/tag/itype/htype/name/id/ac/role/req/vis/label/
    lstrat/section/nearby/opts/desc/placeholder).

    Returns {"category": str, "confidence": float, "rule": str, "key": str}
    on a resolved decision, or {"category": None, "confidence": 0.0,
    "rule": None, "key": None} (UNKNOWN) if no rule matches.

    confidence is included from day one even though this baseline always
    emits 1.0 for a resolved match / 0.0 for UNKNOWN — P1.4's interpreter
    won't be purely deterministic (multi-signal tiers, partial agreement),
    and replay needs to be able to answer "what happens if we reject
    predictions below confidence X" without a breaking interface change
    later. Cheap to add now, expensive to retrofit once callers depend on
    the shape.

    Only the "confirm" bucket produces a real topic category here. "reject"
    (known non-fields) and "special" (structural patterns: other_followup,
    honeypot, etc.) are surfaced via ground_truth_lookup() for replay's own
    bucketing, not returned as a predicted category by this baseline
    interpreter, since a real interpreter isn't expected to predict
    "reject"/"special" as if they were topic answers.
    """
    gt = ground_truth_lookup(field)
    if gt["bucket"] == "confirm":
        return {"category": gt["category"], "confidence": 1.0, "rule": gt["rule"], "key": gt["key"]}
    return {"category": None, "confidence": 0.0, "rule": None, "key": None}
