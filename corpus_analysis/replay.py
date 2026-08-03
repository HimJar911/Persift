"""P1.3 — Replay harness.

Runs an interpret(field) -> category function (default: interpreter_baseline)
over the full corpus and scores it against the human-verified answer key
(cluster_decisions_v2.json), via interpreter_baseline.ground_truth_lookup().
This is what makes every future P1.4 interpreter change measurable instead
of a guess (FORM_ENGINE_DESIGN.md standing rule: "did UNKNOWN go down
without hurting the others").

Ground truth is looked up via interpreter_baseline.ground_truth_lookup(),
kept structurally separate from whatever --interpreter's interpret()
implements — see that function's docstring for why (they only agree by
construction for the baseline; a smarter P1.4 interpreter must not be able
to silently redefine ground truth by changing its own key derivation).

**Vocabulary note (added for P1.4):** ground_truth_lookup() returns
categories in taxonomy_v1's ONTOLOGY vocabulary (that's what
cluster_decisions_v2.json's "confirm" bucket was built with). P1.4's
interpret() deliberately emits resolveValue()'s CAPABILITY vocabulary
instead (see corpus_analysis/category_mapping.py + the P1.4 plan's
"category vocabulary" decision) — the two vocabularies use different names
for the same underlying facts in most cases. Comparing a capability-name
prediction directly against an ontology-name ground truth would show
100% mismatch even for a flawless interpreter. So replay translates
ground truth through category_mapping.capability_for() before comparing —
scoring "did the interpreter correctly identify the CAPABILITY this field
maps to," which is what actually matters for autofill. A field whose
ontology category has no capability (UNSUPPORTED) is excluded from
topic-category scoring entirely (folded into gt_reject_or_special, since
"the answer key resolves to something the product can't act on yet" is
the same shape as "not a real question" from interpret()'s point of view —
neither should be scored as a coverage gap interpret() could have closed).

Run:
    python replay.py [--interpreter MODULE] [--sample-out PATH] [--top-confusions N]

Reads:  oc_compact_full_v2.json, cluster_decisions_v2.json (via
        interpreter_baseline's module-level load)
Writes: replay_report.json (+ optional sample-mismatches file)
"""

import argparse
import importlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import taxonomy_v1
from category_mapping import capability_for
from interpreter_baseline import ground_truth_lookup

BASE = Path(__file__).parent


def load_corpus():
    with open(BASE / "oc_compact_full_v2.json", encoding="utf-8") as f:
        companies = json.load(f)
    fields = []
    for ci, c in enumerate(companies):
        for fi, f in enumerate(c["fields"]):
            fields.append({"company": c["company"], "job_id": c["job_id"], "ci": ci, "fi": fi, "field": f})
    return fields


def corpus_version_tag():
    """Cheap, deterministic fingerprint of the compact corpus file — not a
    full content hash (would be slow at 632K fields for little benefit),
    just size + mtime, enough to notice "this ran against a different
    regeneration of the corpus" when comparing reports across time.
    """
    p = BASE / "oc_compact_full_v2.json"
    st = p.stat()
    return f"size={st.st_size}:mtime={int(st.st_mtime)}"


def run_replay(interpret_fn, sample_out=None, sample_size=25, top_confusions=20):
    records = load_corpus()

    counts = Counter()
    per_category = {}  # category -> {"gt_count": int, "match": int, "mismatch": int}
    confusion = Counter()  # (gt_category, predicted_category) -> count
    samples = {"mismatch": [], "predicted_unknown_gt_resolved": []}

    for rec in records:
        field = rec["field"]
        gt = ground_truth_lookup(field)
        pred = interpret_fn(field)

        gt_bucket = gt["bucket"]
        gt_category = gt["category"]
        pred_category = pred["category"]

        if gt_bucket in ("reject", "special"):
            # Not a topic-category question — score separately, never as a
            # topic-category miss (a "reject"/"special" field predicted as
            # UNKNOWN by the interpreter is CORRECT behavior, not a gap).
            counts["gt_reject_or_special"] += 1
            if gt_bucket == "reject" and pred_category is not None:
                # Interpreter confidently assigned a topic category to a
                # field the answer key says isn't a real question at all —
                # a real defect, tracked distinctly from ordinary mismatch.
                counts["predicted_category_for_rejected_field"] += 1
            continue

        if gt_bucket != "confirm":
            # Ground truth itself doesn't resolve (not_found / no rule
            # matched) — this is the corpus's own residual, not scored as
            # an interpreter error either way.
            counts["both_unknown" if pred_category is None else "predicted_resolved_gt_unknown"] += 1
            continue

        # gt_bucket == "confirm": the answer key resolves to a real
        # ontology category. Translate it to the resolveValue CAPABILITY
        # vocabulary before scoring, since that's what interpret() actually
        # emits (see module docstring's "Vocabulary note"). If the ontology
        # category has no capability yet (UNSUPPORTED), this field isn't a
        # topic-category coverage gap interpret() could ever close — fold
        # it into gt_reject_or_special rather than counting it against
        # coverage/mismatch. NOTE: predicting a category here is NOT a
        # defect the way it is for a real "reject" field (an actual
        # non-question) — the interpreter may have correctly identified
        # the field's meaning, the product just has no capability for it
        # yet. Tracked as its own counter, kept separate from
        # predicted_category_for_rejected_field (which stays reserved for
        # the real "classified a non-question as a question" defect).
        gt_capability = capability_for(gt_category)
        if gt_capability is None:
            counts["gt_reject_or_special"] += 1
            counts["gt_unsupported_ontology_category"] += 1
            if pred_category is not None:
                counts["predicted_category_for_unsupported_field"] += 1
            continue

        per_category.setdefault(gt_capability, {"gt_count": 0, "match": 0, "mismatch": 0, "predicted_unknown": 0})
        per_category[gt_capability]["gt_count"] += 1

        if pred_category is None:
            counts["predicted_unknown_gt_resolved"] += 1
            per_category[gt_capability]["predicted_unknown"] += 1
            if sample_out and len(samples["predicted_unknown_gt_resolved"]) < sample_size:
                samples["predicted_unknown_gt_resolved"].append({
                    "job_id": rec["job_id"], "company": rec["company"],
                    "field": field, "ground_truth_ontology": gt_category,
                    "ground_truth_capability": gt_capability, "predicted": None,
                })
        elif pred_category == gt_capability:
            counts["match"] += 1
            per_category[gt_capability]["match"] += 1
        else:
            counts["mismatch"] += 1
            per_category[gt_capability]["mismatch"] += 1
            confusion[(gt_capability, pred_category)] += 1
            if sample_out and len(samples["mismatch"]) < sample_size:
                samples["mismatch"].append({
                    "job_id": rec["job_id"], "company": rec["company"],
                    "field": field, "ground_truth_ontology": gt_category,
                    "ground_truth_capability": gt_capability, "predicted": pred_category,
                })

    total_topic_fields = sum(v["gt_count"] for v in per_category.values())
    total_match = counts["match"]
    total_mismatch = counts["mismatch"]
    total_pred_unknown = counts["predicted_unknown_gt_resolved"]

    coverage_pct = (100.0 * total_match / total_topic_fields) if total_topic_fields else 0.0
    mismatch_pct = (100.0 * total_mismatch / total_topic_fields) if total_topic_fields else 0.0
    unknown_pct = (100.0 * total_pred_unknown / total_topic_fields) if total_topic_fields else 0.0

    per_category_report = {}
    for cat, v in sorted(per_category.items()):
        gt_count = v["gt_count"]
        per_category_report[cat] = {
            "gt_count": gt_count,
            "match": v["match"],
            "mismatch": v["mismatch"],
            "predicted_unknown": v["predicted_unknown"],
            "coverage_pct": round(100.0 * v["match"] / gt_count, 2) if gt_count else None,
            "mismatch_pct": round(100.0 * v["mismatch"] / gt_count, 2) if gt_count else None,
        }

    top_confusion_pairs = [
        {"ground_truth": gt_cat, "predicted": pred_cat, "count": n}
        for (gt_cat, pred_cat), n in confusion.most_common(top_confusions)
    ]

    report = {
        "corpus_version": corpus_version_tag(),
        "taxonomy_version": taxonomy_v1.TAXONOMY_VERSION,
        "interpreter": interpret_fn.__module__,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_fields": len(records),
        "total_topic_fields_scored": total_topic_fields,
        "gt_reject_or_special_fields": counts["gt_reject_or_special"],
        "gt_unsupported_ontology_category_fields": counts["gt_unsupported_ontology_category"],
        "predicted_category_for_rejected_field": counts["predicted_category_for_rejected_field"],
        "predicted_category_for_unsupported_field": counts["predicted_category_for_unsupported_field"],
        "both_unknown_fields": counts["both_unknown"],
        "predicted_resolved_gt_unknown_fields": counts["predicted_resolved_gt_unknown"],
        "coverage_pct": round(coverage_pct, 2),
        "mismatch_pct": round(mismatch_pct, 2),
        "predicted_unknown_pct": round(unknown_pct, 2),
        "per_category": per_category_report,
        "top_confusion_pairs": top_confusion_pairs,
    }

    if sample_out:
        with open(sample_out, "w", encoding="utf-8") as f:
            json.dump(samples, f, indent=2, ensure_ascii=False)

    return report


def main():
    parser = argparse.ArgumentParser(description="P1.3 replay harness")
    parser.add_argument("--interpreter", default="interpreter_baseline",
                         help="module (importable from corpus_analysis/) exposing interpret(field)")
    parser.add_argument("--sample-out", default=None,
                         help="path to write sample mismatch/predicted-unknown fields for manual review")
    parser.add_argument("--sample-size", type=int, default=25)
    parser.add_argument("--top-confusions", type=int, default=20)
    parser.add_argument("--report-out", default=str(BASE / "replay_report.json"))
    args = parser.parse_args()

    sys.path.insert(0, str(BASE))
    module = importlib.import_module(args.interpreter)
    interpret_fn = module.interpret

    report = run_replay(
        interpret_fn,
        sample_out=args.sample_out,
        sample_size=args.sample_size,
        top_confusions=args.top_confusions,
    )

    with open(args.report_out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"interpreter: {report['interpreter']}")
    print(f"total fields: {report['total_fields']}")
    print(f"topic fields scored: {report['total_topic_fields_scored']}")
    print(f"coverage: {report['coverage_pct']}%")
    print(f"mismatch: {report['mismatch_pct']}%")
    print(f"predicted-unknown (gt resolved): {report['predicted_unknown_pct']}%")
    print(f"reject/special fields (not scored as topic): {report['gt_reject_or_special_fields']}")
    print(f"  of which unsupported ontology category (no live capability yet): {report['gt_unsupported_ontology_category_fields']}")
    print(f"    of which interpreter still predicted a category (not a defect — capability gap, not a misread): {report['predicted_category_for_unsupported_field']}")
    print(f"  of which a genuine reject-bucket field got wrongly assigned a category (real defect): {report['predicted_category_for_rejected_field']}")
    print(f"both-unknown (corpus residual): {report['both_unknown_fields']}")
    print(f"predicted-resolved but gt-unknown (interpreter beat the answer key): {report['predicted_resolved_gt_unknown_fields']}")
    if report["top_confusion_pairs"]:
        print("\ntop confusion pairs (ground_truth -> predicted, count):")
        for pair in report["top_confusion_pairs"][:10]:
            print(f"  {pair['ground_truth']} -> {pair['predicted']}: {pair['count']}")
    print(f"\nfull report written to {args.report_out}")
    if args.sample_out:
        print(f"sample mismatches written to {args.sample_out}")


if __name__ == "__main__":
    main()
