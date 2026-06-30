# Persift — Target Architecture: Design Notes (IN PROGRESS)

> **Status: work-in-progress design discussion.** This captures decisions locked through discussion on June 30, 2026. It is NOT the current architecture — it's the *target*. Current state lives in CLAUDE.md / ARCHITECTURE.md / STATE.md. When this design is complete and approved, it becomes `TARGET_ARCHITECTURE.md` and we write a migration path from today's code to it.
>
> **How these decisions were made:** discussion-first. Each was explained, debated, and approved by the founder before being recorded here. Do not change anything here without the same process.

---

## Working method (the meta-lesson — keep doing this)

The root cause of the architectural drift was a workflow: "here's the problem, fix it" → the tool takes the shortest path → locally-optimal shortcuts accrete into global mess (e.g. a field landing in two homes). **Fix: decide the approach in discussion FIRST, then ask for execution.** This whole design was built that way and it must continue that way.

---

## Domain model — 6 first-class entities

| Entity | What it is |
|---|---|
| **Student** | B2C user. Profile + resume + preferences. |
| **Company** | Employer. Polled for jobs. Has many Jobs. |
| **Job** | One open role. Identified by *apply target*. Has discovery source(s) + apply target as separate facts. |
| **Application** | **The central object.** A Student↔Job pairing the system acts on. Carries the lifecycle. *(lifecycle design pending — next session)* |
| **Outcome** | What happened to an Application (interview / rejection / silence). The product moat. *(design pending)* |
| **Field Correction** | Per-Application record of what the system filled vs. what the user submitted. Feedback loop on fill quality. *(design pending)* |

**Deferred, with hooks (NOT built):** Institution / Cohort. The product is **pure B2C right now** — institutional demand is unvalidated. Hook for a future pivot = capture `university` (+ grad year) on the Student. No institution/cohort tables until demand is validated.

**Two data-capture purposes — kept architecturally separate:**
- **(A) Product / ML loop** — operational, in the app DB, tied to Application + Outcome + Field Correction. Improves tailoring/fill from results.
- **(B) Business growth metrics** — signups, activation, applications/user, interview rate, fill accuracy. THIS SESSION: define which metrics + ensure raw events are captured. DEFER the analytics system/dashboards.

---

## The governing rule — Column vs JSONB (kills the dual-home bug class)

> **A field is a COLUMN** if anything other than the form-filler reasons about its value — the matcher filters on it, the ML records it, a growth metric counts/correlates it, or the DB should enforce its type/presence.
>
> **A field is JSONB** if it is only ever stored and handed back whole — written at signup, read by the extension to fill a form, never queried/filtered/sorted/counted.
>
> **No field lives in both. Each fact has exactly one home.**

This single rule makes the June-2026 JSONB-vs-columns drift bug *structurally impossible*. The bug happened because the same fact (university, sponsorship, etc.) lived in both a column AND the `application_settings` JSONB, and the two drifted.

---

## Student entity — field homes (LOCKED)

**COLUMNS** (system reasons about them):
`email`, `tier`, `university`, `major`, `gpa`, `graduation_date`, `needs_sponsorship`, `visa_type`, `resume_text`, `location_city`, `location_state`, `location_preference` *(NEW: local | remote | anywhere — asked at signup, drives matcher)*

**JSONB** (form-fill carry-along, never queried):
`eeo_*` (gender/race/hispanic/veteran/disability), `linkedin_url`, `github_url`, `preferred_name`, `previous_employers`, immigration explanation text, compensation fallback (see below)

**ELIMINATED:**
- `custom_answers` (the 24 stored essay answers) → **replaced by LLM generation** (see below)
- `QUESTION_ALIASES` (fuzzy-match map) → **gone** — no longer matching form questions to stored keys
- `desired_hourly_min/max` as stored student data → **computed per-job from the JD** at fill time

---

## Free-text form questions — LLM-generated, not stored (LOCKED)

The old model: student pre-writes 24 canned essay answers at signup; extension fuzzy-matches a form question to a saved key and pastes it. **Rejected** — brutal onboarding, brittle matching, generic templated output, never a complete list.

**New model:** when the filler hits a free-text question it can't answer from a profile column, it calls the LLM with `resume + profile + job description + the literal question text` and generates a tailored, job-specific answer.

- Eliminates the onboarding burden, the `custom_answers` store, and the `QUESTION_ALIASES` map.
- **Status: designed now, IMPLEMENTED when the Anthropic key lands** — same deferral as L4 resume tailoring.

---

## Compensation — computed, not stored (LOCKED)

Desired compensation is **not a student attribute.** Approach: read the job's salary range from the JD, fill the average. Keep an **optional JSONB min/max as fallback** only for forms where the JD has no range. Not a column; not core student data.

---

## Field Correction — new first-class entity (LOCKED in principle, mechanism pending)

Track, per Application, **what the system filled vs. what the user actually submitted**, for users who manually review before submitting. Goal: drive the correction rate toward zero so review becomes unnecessary (and auto-apply becomes safe to push).

- Highest-quality fill-quality training signal, generated free by normal usage. Defensible/moat data (on-device competitors can't collect it centrally).
- Bridges purpose (A) product-ML AND (B) growth metric ("fill accuracy = % fields submitted unedited").
- **Mechanism (committed, has a cost):** the extension snapshots form state **twice** — right after fill, and at submit — and diffs them. Build later; architect the entity + capture now.

Note: review is a per-Application toggle (auto-apply on = no review; off = user reviews & clicks submit). There is NO per-question review UI — *what* the user changed is captured by the snapshot diff, not by asking them.

---

## Job entity — LOCKED

**Identity:** apply target — the real ATS + that ATS's native job id (e.g. `greenhouse / 789`). Where you APPLY, not where you found it.

**Two separate facts (previously conflated in the single `ats` field):**
- **Discovery source(s)** — a *list*: how Persift found it (`jobright`, `greenhouse-direct`, …). Provenance + metrics ("is Jobright worth paying for?").
- **Apply target** — real ATS + `apply_url`. What the extension needs.

**Dedup:** one real-world role = one Job regardless of how many sources surface it. A second source appends to the sources list — no new row. Kills the double-apply-to-same-role bug present in today's `(job_id, ats)` keying.

**Jobright resolution timing — Flow A (resolve, then insert):**
Jobright job → `discovery_staging` → resolve apply URL → dedup against `jobs` → promote with true identity. The real `jobs` table only ever holds clean, fully-identified, deduplicated jobs. Nothing references a job until its identity is known. (Rejected Flow B "insert provisionally, fix on resolve" — it lets relationships form around a misidentified row, forcing bug-prone post-hoc merge/rekey.)

---

## Two pipelines, separated (LOCKED)

`discovery_staging` is currently OVERLOADED — serving both purposes below and doing neither well.

1. **Job ingestion** (NEW pipeline, Flow A): Jobright → staging → resolve apply URL → dedup → promote to `jobs`. **Currently broken in production:** Jobright jobs are staged but never resolved/deduped/promoted because Worker A (which would process them) is disabled — they rot in `discovery_staging`. This pipeline fixes that.
2. **Company discovery** (Worker A): find which companies exist + their ATS, to build the poll list. Independently broken (depends on an unbuilt BuiltWith integration). **Noted, NOT solved in this design pass.**

Target: these become two distinct pipelines; `discovery_staging` stops being a shared dumping ground.

---

## Still to design (next sessions)

1. **Application lifecycle (THE BIG ONE)** — status flow done right; who owns each transition. Currently tangled across matcher → tailor_worker → server.py → extension.
2. **Outcome capture** — how signals attach to Applications; the Gmail-parsing piece. The moat.
3. **Field Correction mechanism** — the two-snapshot diff, in detail.
4. **Pipeline & entry points** — resolve main.py vs discovery_runner.py duplication.
5. **Contracts** — API↔extension; (B) growth-metrics raw-event capture.
6. **Migration path** — ordered, safe steps from today's code to this target.

---

## Open threads to revisit

- Company discovery / Worker A / BuiltWith is broken — needs its own design pass.
- `config.py` still gpt-4o (deliberate — switching to Claude at tailoring time).
- `main.py process_single_job` tailoring commented out (deliberate — tailoring not built yet).
- Hard constraint: **July 27 tech-week pitch** (a demo + story, not a finished platform). July 15 launch is now flexible — architecture drives the date, not vice versa.
