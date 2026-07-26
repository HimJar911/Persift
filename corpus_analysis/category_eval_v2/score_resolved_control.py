"""One-off scoring script for the v2 resolved-control block (not part of the
regular pipeline — same throwaway pattern as the batch/label files it reads).
Merges all gt100_batch_*_labels.jsonl + patch files by job_id against the
source rows' current_tier12_categories, then computes Tier 1+2 precision
metrics the same way the 77-job v1 clean sample was scored: exact match,
any-overlap, confidently-wrong, abstain rate. Excludes resolved-bucket rows
where current_tier12_categories is empty (the known v1 sampling bug)."""

import json
import glob


def load(fn):
    with open(fn, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def main():
    gt = {}
    label_files = sorted(
        glob.glob("corpus_analysis/category_eval_v2/gt_labels/gt100_batch_*_labels.jsonl")
    ) + [
        "corpus_analysis/category_eval_v2/gt_labels/gt100_patch_missing_labels.jsonl",
        "corpus_analysis/category_eval_v2/gt_labels/gt100_single_patch_labels.jsonl",
    ]
    for fn in label_files:
        for r in load(fn):
            gt[r["job_id"]] = r

    src = {}
    for fn in sorted(glob.glob("corpus_analysis/category_eval_v2/gt_batches_b100/gt100_batch_*.jsonl")):
        for r in load(fn):
            src[r["job_id"]] = r

    resolved_ids = [jid for jid, r in src.items() if r["bucket"] == "resolved_control_v2"]
    print(f"resolved_control_v2 rows in source: {len(resolved_ids)}")
    print(f"total ground-truth labels available: {len(gt)}")

    missing_gt = [jid for jid in resolved_ids if jid not in gt]
    print(f"resolved rows missing a ground-truth label: {len(missing_gt)}")

    empty_tier12 = [
        jid for jid in resolved_ids
        if jid in gt and not src[jid]["current_tier12_categories"]
    ]
    print(f"resolved rows with EMPTY current_tier12_categories (sampling-bug exclusion): {len(empty_tier12)}")

    scoreable = [
        jid for jid in resolved_ids
        if jid in gt and src[jid]["current_tier12_categories"]
    ]
    print(f"scoreable rows (resolved, labeled, non-empty tier1+2): {len(scoreable)}")

    exact = 0
    any_overlap = 0
    confidently_wrong = 0
    abstain = 0

    for jid in scoreable:
        tier12 = set(src[jid]["current_tier12_categories"])
        truth = set(gt[jid]["llm_categories"])

        if not truth:
            abstain += 1
            continue

        if tier12 == truth:
            exact += 1

        if tier12 & truth:
            any_overlap += 1
        else:
            confidently_wrong += 1

    n = len(scoreable)
    print()
    print(f"=== Tier 1+2 precision on v2 resolved-control block (n={n}) ===")
    print(f"exact match:         {exact}/{n} = {exact/n*100:.1f}%")
    print(f"any-overlap:         {any_overlap}/{n} = {any_overlap/n*100:.1f}%")
    print(f"confidently-wrong:   {confidently_wrong}/{n} = {confidently_wrong/n*100:.1f}%")
    print(f"abstain (gt empty):  {abstain}/{n} = {abstain/n*100:.1f}%")


if __name__ == "__main__":
    main()
