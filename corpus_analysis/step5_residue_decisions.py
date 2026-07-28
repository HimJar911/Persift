"""Step 5 residue classification decisions — the full-volume corpus
extension's LLM-assisted classification pass over
residue_for_llm_pass.json's `kept` list (English-language, non-junk,
non-malformed residue that didn't cluster deterministically).

Method (per STATE.md's plan): classify against taxonomy_v1
(+ PROPOSED_V2_ADDITIONS for genuinely new categories found along the way),
schema-constrained (validated against the real enum, same discipline as
pollers/llm_classifier.py's classify_batch), with raw-HTML/field-context
verification for any cross-company pattern claim — same standing rule as
the original department_interest correction.

Each entry: {"job_id", "field_id_hash", "occurrence_index", "action":
"confirm"|"reject", "category": <taxonomy key or None>, "note": <evidence>,
"decision_source": "llm_first_pass"|"html_verified"|"founder_verified",
"taxonomy_version": "v1"|"v1+proposed"}

Written incrementally as groups get resolved during this session.
"""

DECISIONS = []


def confirm(field_id_hash, category, note, n_instances=1, taxonomy_version="v1"):
    DECISIONS.append({
        "field_id_hash": field_id_hash,
        "action": "confirm",
        "category": category,
        "note": note,
        "n_instances": n_instances,
        "decision_source": "html_verified",
        "taxonomy_version": taxonomy_version,
    })


def reject(field_id_hash, note, n_instances=1):
    DECISIONS.append({
        "field_id_hash": field_id_hash,
        "action": "reject",
        "category": None,
        "note": note,
        "n_instances": n_instances,
        "decision_source": "html_verified",
        "taxonomy_version": "v1",
    })


# --- Privacy policy consent (Qube Research and Technologies, Axon) ---
confirm(
    ["3b725c88", "d1c428a6", "3bf88def", "e242a2be"],  # representative hashes seen across the 230-field group; full set has more per-page unique hashes since checkbox_group elements often hash uniquely per instance
    "consent_privacy_policy",
    "230 instances across 2 companies (Qube Research and Technologies, "
    "Axon) — checkbox_group whose only content is a section header "
    "literally reading 'Privacy Policy *', no label/options/nearby text. "
    "New category, not in original taxonomy_v1 — added as "
    "PROPOSED_V2_ADDITIONS.",
    n_instances=230,
    taxonomy_version="v1+proposed",
)
