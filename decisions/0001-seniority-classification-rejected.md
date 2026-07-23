# 0001 — Categorical seniority classification rejected in favor of literal YoE extraction

**Date:** 2026-07-21
**Status:** accepted (final design), supersedes an earlier built-and-discarded design
**Files:** `pollers/seniority.py`, migration 022 (v2), migration 023

## Context

The matcher needed some notion of job seniority/experience level to filter
matches. The original field it read (`experience_level` / `job_types`
comparison) was dead — never populated by any onboarding flow.

## First design (built, then rejected)

A categorical `seniority_level` enum: `intern / new_grad / entry_level /
mid_level / senior_level / executive / not_applicable / unknown`, inferred
from job titles. Built, schema-migrated (migration 022 v1), even live-tested
via a Haiku subagent.

**Killed by real ground truth**: pulled 4,323 real SmartRecruiters jobs
(which carry an employer-declared `experienceLevel` field) and found 124
real "Director"-titled jobs split **50% executive / 24% mid_level / 24%
entry-or-not_applicable**. Even a real employer's own label is genuinely
ambiguous for a huge class of titles — any classifier (regex, LLM, human)
guessing one bucket from title alone would be confidently wrong on roughly
half of them.

**Founder's explicit call:** never guess, only store what a posting
literally states. See `[[feedback_never_infer_only_extract]]` memory.

## Final design (built, live)

`pollers/seniority.py`: exactly one function, `extract_years_of_experience(*texts)`
— pure regex extraction of literal "N years of experience" / "N-M years of
experience" phrases, zero inference from tone/scope/responsibilities. Feeds
`jobs.years_of_experience_min/max` (nullable smallint, migration 022 v2 —
the v1 categorical columns were dropped, all-NULL so no data lost).

Real coverage measured twice, consistently: **38.9%** of real jobs state an
explicit number; the other ~61% get `NULL` on both columns — treated as "not
stated," never "unknown, guess something."

`users.years_of_experience` added (migration 023) as the user-side
counterpart. `pipeline/matcher.py`'s hard filter #4 repointed:
`user_yoe < job_yoe_min`, but only excludes when **both** sides have real
data — either side NULL passes through unfiltered on this axis.

## Rejected approaches — don't re-propose

- "Infer an approximate range from context/scope" — explicitly rejected,
  "we should never infer anything at all."
- "Anchor-required inference with a cited phrase" — same rejection, tighter
  framing didn't save it. The founder's line is inference itself, not just
  unanchored inference.
