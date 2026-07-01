# Persift — Target Architecture: Design Notes (IN PROGRESS)

> **Status: work-in-progress design discussion.** This captures decisions locked through discussion on June 30, 2026. It is NOT the current architecture — it's the *target*. Current state lives in CLAUDE.md / ARCHITECTURE.md / STATE.md. When this design is complete and approved, it becomes `TARGET_ARCHITECTURE.md` and we write a migration path from today's code to it.
>
> **How these decisions were made:** discussion-first. Each was explained, debated, and approved by the founder before being recorded here. Do not change anything here without the same process.

---

## ▶ START HERE NEXT (handoff — read before doing anything)

**You are the next agent picking this up. Read this whole file top-to-bottom first — it's the full context; the conversation that produced it is gone.**

**The discipline is non-negotiable (see "Working method" below):** discussion-first. Explain each option, let the founder debate and approve, THEN record. Do NOT write code or edit design decisions unilaterally. Keep responses tight — the founder disengages from walls of text; lead with the decision, not the survey.

**Locked so far (do not reopen without the founder):**
1. Domain model — 6 entities · Column-vs-JSONB rule · Student fields · LLM free-text · computed comp · Job identity · two pipelines.
2. **Application lifecycle** — state set (7 phases, 3 spans) + transitions + ownership + retry. COMPLETE.
3. **Outcome capture** — append-only stream, 3 sources, source→type constraint, A/B/C/D data framing, 2 scope decisions. COMPLETE.
4. **Field Correction mechanism** — two-snapshot diff. COMPLETE except ONE open call ↓.

**Pick up EXACTLY here — first action tomorrow:**
- **(a) OPEN DECISION to settle first:** Field Correction entity home — dedicated `field_corrections` table vs reuse `application_events`. Recorded lean: dedicated (PII isolation). Get the founder's ruling, record it. (~5 min)
- **(b) Then, remaining sections in order** (est. ~1.5–2 hrs total, discussion-first):
  1. **Pipeline & entry points** (~20–30 min) — main.py vs discovery_runner.py duplication; the two-pipeline split (job ingestion Flow A vs company discovery).
  2. **Contracts** (~30–45 min) — API↔extension. **Heaviest.** The queue endpoint becomes an atomic claim (`UPDATE...RETURNING` + `FOR UPDATE SKIP LOCKED`), NOT a `GET` — carried from the lifecycle section. Every renamed status ripples here.
  3. **Migration path** (~30–45 min) — ordered safe steps from today's code (1 user, ~18K jobs — lots of leverage) to this target. Depends on Contracts being final.
- **Watch for:** Contracts or Migration may surface something that reopens the lifecycle (e.g. the atomic-claim ripple). That's the good kind of catch — on paper, not in code. Flag it, don't paper over it.

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

## Application lifecycle — the state set (LOCKED; transitions/ownership pending)

**Governing principle — one axis per home (kills the overloaded-`status` bug class):**
- **Axis A — lifecycle phase** → lives in `status`. Small, mostly-linear set below.
- **Axis B — outcome** (what the employer did: interview / rejection / silence) → the **Outcome** entity, NOT `status`. A mechanical failure must never be able to write a fake employer outcome.
- **Axis C — failure cause** (tailor crashed, form broke, tab closed, user skipped, timed out) → a `failure_reason` field, NOT its own status.

`status` models axis A only.

**Three custodial spans — System → Client → World.** The System→Client handoff is the most important event in the lifecycle; no single status may straddle it (this is exactly what today's `applying` gets wrong by naming both "backend finished" and "client filling").

| Phase | Span | Meaning | Sole writer |
|---|---|---|---|
| `matched` | System | Pairing created by matcher; not yet tailored. The tailor's work queue. | matcher |
| `preparing` | System | Tailor picked it up; resume being built. **Kept solely for crash-recovery** — distinguishes "never started" (`matched`, safe to re-run) from "started and died" (`preparing`, may have a partial artifact; clean before retry). | tailor_worker |
| `ready` | System→Client handoff | Tailored artifact on disk; this is what the extension queue returns. (The honest half of today's `applying`.) | tailor_worker |
| `submitting` | Client | Extension claimed it and is actively filling. (The other half of today's `applying`, now separate.) | extension |
| `awaiting_review` | Client/User | Filled, auto-submit OFF — parked for the user to review & submit. **Distinct from `ready`** (waits on a human, not a machine; counted separately for the correction-rate metric). Unlike today's `needs_review`, it HAS an exit. | extension |
| `submitted` | Client→World handoff | Form confirmed submitted. **Terminal for `status`.** Hands off to the Outcome entity. (Replaces `applied` — which lied, meaning "we submitted," not "employer accepted".) | extension |
| `abandoned` | any | Did not complete, for ANY mechanical/user reason. **Collapses today's `failed` + `failed_stale` + `expired` into one phase**; the *why* is `failure_reason`, the *how long stuck* is timestamps. Retryable per policy. | whoever detects it |

**Not a status (parked in its correct home):**
- *why it failed* → `failure_reason` field (axis C)
- *what the employer did* → **Outcome** entity (axis B)
- *auto vs review vs notify-only* → **`submission_mode`** flag on the Application (today's `notify_only` was a non-phase wearing a status)
- *stuck duration / retries* → timestamps + `retry_count`

**Bugs in today's model this design kills** (found by reading matcher/tailor_worker/server/background/main, June 30):
1. `applying` means two things (backend-ready AND client-filling) → split into `ready` + `submitting`.
2. cleanup runs the 48h `expired` sweep before the 1h `failed_stale` sweep; the comment describes the opposite of what the code does; both are just "extension never finished" → collapsed into `abandoned`.
3. `mark_failed` writes an `application_outcomes` row `outcome_type='rejected'` for EVERY failure incl. `user_skipped`/tailor-crash → **poisons the moat with fake rejections.** Fixed by keeping outcome out of the failure path (axis B ≠ axis C).
4. `needs_review` is a dead-end — no endpoint exits it, not in 90-day cleanup → `awaiting_review` gets an exit.
5. `notify_only` is a parallel track wearing a status → now a `submission_mode` flag.

**Edges still open** (later sections may revise): `awaiting_review`/`submitting` boundary may shift when the Field-Correction two-snapshot moment is pinned. (`abandoned` retryable-vs-terminal is now RESOLVED below — retry count decides, not a separate state.)

---

## Application lifecycle — transitions & ownership (LOCKED)

**Rule: every legal edge has exactly one writer.** Today's bug is 4 writers on one column stepping on each other; this assigns a single owner per edge.

```
matched → preparing → ready → submitting ─┬─▶ submitted            (auto-submit ON)
   │          │                  ↑ │       └─▶ awaiting_review → submitted   (review OFF)
   │          │                  │ └─(heartbeat renews lease)
   │          ▼                  │
   └──────▶ abandoned ◀──────────┘   (lease expired / released / tailor crash)
              │
              └──▶ ready   (retry, mechanical reason — artifact still good, no re-tailor)
```

| Edge | Trigger | Sole writer |
|---|---|---|
| → `matched` | pairing created | matcher |
| `matched → preparing` | claimed for tailoring | tailor_worker |
| `preparing → ready` | artifact written | tailor_worker |
| `preparing → abandoned` | tailor crashed (self-reported, in-process) | tailor_worker |
| `ready → submitting` | extension claims (atomic, lease stamped) | extension |
| `submitting → submitting` | heartbeat renews lease | extension |
| `submitting → submitted` | confirmed submit (auto) | extension |
| `submitting → awaiting_review` | filled, review-off | extension |
| `awaiting_review → submitted` | user submits | extension |
| `submitting → abandoned` | lease expired / released | **cleanup ONLY** |
| `abandoned → ready` | retry, mechanical reason | cleanup/retry |

**Mechanisms:**

1. **Atomic claim (kills double-apply).** The claim is read+write in ONE statement so only one winner exists. The queue endpoint stops being a `GET` (read) and becomes an atomic `UPDATE ... RETURNING` using `FOR UPDATE SKIP LOCKED`:
   ```sql
   UPDATE user_jobs SET status='submitting', lease_expires_at=NOW()+INTERVAL '10 min'
   WHERE id = (SELECT id FROM user_jobs WHERE user_id=$1 AND status='ready'
               ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1)
   RETURNING ...;
   ```
   Reason: today's `GET /jobs/queue` (SELECT `applying`) has a read-then-act gap — two pollers can both read `ready` before either writes, and double-apply. `SKIP LOCKED` makes the DB the single arbiter. **This reshapes the API↔extension contract — carry to the Contracts section.**

2. **Lease = 10 min, renewed by heartbeat.** Reuses the extension's existing heartbeat (`background.js` bumps `phase_started_at`; stale=10min). A `submitting` row whose lease is >10 min stale is dead; cleanup reaps it. **Only the CLIENT span uses the lease.** Backend failures (`preparing → abandoned`) are synchronous and self-reported by tailor_worker in-process — no lease, no cleanup needed. Asymmetry is deliberate: only client-side (across-the-network) deaths need reaping.

3. **Retry: count decides terminal, reason decides target.**
   - Every `abandoned` is retryable → back to `ready` (mechanical reason; artifact on disk is still good, no re-tailor).
   - **`retry_count` cap = 2**, shared by BOTH user-skip and mechanical death (crash/lease-expiry). One counter.
   - **User skip is NOT terminal on first hit** (skips can be accidental). Skip once → back to `ready`, re-served on the very next poll (no backoff — count does the work, not timing). Skip twice → stays `abandoned` = terminal. The second deliberate skip is the signal.
   - Same cap catches a job that crashes the filler twice → terminal (a form that breaks twice is probably broken).
   - Truly-terminal-on-first-hit is reserved for reasons a retry physically cannot fix (posting gone / apply URL dead) — not skip, not crash.

---

## Outcome capture — the moat (LOCKED)

**Foundational principle: Outcome is an append-only event STREAM, never a mutable status.** An Application accretes a stream of outcomes over time; you never overwrite. Wrong outcomes are fixed by appending a *correction* that points at what it corrects (`corrects_outcome_id` chain). This preserves "model said X, truth was Y" — which is itself training data. Much of this is already built in `application_outcomes` (migration 008): 15 outcome types, correction chain, `previous_outcome_type`, structured offer comp, `triggering_signal_id`→`gmail_signals`, and a trigger `trg_update_current_stage` that denormalizes the latest outcome onto `user_jobs.current_stage`.

**Two fields, clean seam (this IS the axis-A/axis-B handoff):**
- `status` (axis A, our lifecycle) — stops at `submitted`.
- `current_stage` (axis B, latest outcome) — `callback`/`interview_stage`/`offer`/`rejected`… **Written ONLY by the outcome trigger.** Nothing else touches it. `status` hands off to Outcome at `submitted`; `current_stage` is Outcome's projection back onto the row.

**Methodology — three SOURCES, one append-only SINK:**

| Source | May write | Confidence |
|---|---|---|
| `extension_detected` | **ONLY `applied_confirmed`** — the one fact the browser directly witnesses. | 1.0 |
| `gmail_auto` | Employer verdicts — email → classify → link to Application → append signal + outcome. | model 0–1 |
| `manual` | **Corrections ONLY** (user one-taps to fix a wrong Gmail classification). NOT self-reporting. | 1.0 |

> **Schema teeth for the fake-rejection bug (bug #3):** `extension_detected` may ONLY ever write `applied_confirmed`. Employer verdicts (`rejected`/`callback`/`offer`/…) come ONLY from `gmail_auto` or `manual`. This is a source→type constraint (enforce in schema). Today's `mark_failed` writing `rejected` for mechanical failures is exactly what this forbids.

**Gmail path (the moat), two hard problems the schema already anticipates:**
1. **Linkage** — which Application does this email belong to? (`gmail_signals.linked_application_id`; `sender_domain` is the weak key.)
2. **Correction** — model is fallible → `user_confirmed`/`user_correction` on the signal + append-only `corrects_outcome_id` chain on the outcome.

**Velocity is a first-class output.** The moat is not "got a callback" but "callback in 4 days, interview in 2 weeks." Append-only stream + `outcome_date` gives time-in-stage for free (diff consecutive events) — be deliberate that we surface it.

### Data-tracking framing — ONE stream, four read-side purposes (LOCKED)

We do NOT build separate tracking systems. Capture ONE finest-grain event stream; A/B/C/D are all read-side aggregations over it. Aggregating early loses re-sliceability for a purpose (esp. C) we can't fully predict yet.

| | Purpose | Audience | Home / grain |
|---|---|---|---|
| A | Outcome / ML loop | the model | `application_outcomes`, `model_predictions` (individual grain) |
| B | Student insights ("how's *my* search") | student (retention) | read-side: A filtered to `user_id` |
| C | Institutional proof | universities (revenue) | read-side: aggregate over `university`; `aggregate_benchmarks` (k-anon, aggregate-ONLY) |
| D | Business/growth metrics | founder | `application_events`, `user_job_interactions` (behavioral) |

**Consent boundary:** B is "about a student, for the student"; C is "about a student, shown to their university." C must be **aggregate-only / k-anonymous** — individual rows never cross the A/B→C line.

### Scope decisions (LOCKED)
- **No manual logging, ever** (hard product constraint). The only recurring user action is the optional **review-before-submit** step (auto-submit off). Everything else is one-time (signup + Gmail OAuth) or passive.
- **No non-Persift baseline capture** — we cannot capture applications the user sent outside Persift. **Consequence (known, not a bug):** the university pitch (C) CANNOT show with-vs-without lift. Only internal contrast (applied-vs-skipped, cohort-over-time) and absolute numbers. Decided consciously.
- **This session = design purpose A; ensure grain is fine enough to serve B/C/D later.** B/C/D fully specced later, read-side.

---

## Field Correction ↔ lifecycle reconciliation (LOCKED)

Field Correction (two-snapshot diff, locked earlier) lands cleanly on the `awaiting_review → submitted` edge — the boundary does NOT shift:
- fill done → **snapshot #1** → status `awaiting_review`
- user edits + clicks submit → **snapshot #2** → **diff = what the user changed** → append Field Correction record + status `submitted`

No per-question UI; the diff IS the capture. Only occurs when review is on (auto-submit off). Feeds the "correction rate → zero" metric (fill accuracy = % fields submitted unedited).

---

## Field Correction mechanism — the two-snapshot diff (LOCKED; entity home open)

**The two snapshots:**
- **#1 = what Persift filled.** Taken when autofill completes, before the user touches anything.
- **#2 = what got submitted.** Taken on the Submit click, capture-phase, before navigation.
- **Diff(#1, #2) = exactly what the user changed on review = the correction signal.** Only occurs when auto-submit is OFF (`awaiting_review`).

**Field identity (the diff's join key):** key each field on **classified category + label text** (both already computed by `filler_utils`). Stable across both snapshots AND meaningful ("user changed the *sponsorship* answer") — a DOM path would match but carry no signal. A snapshot = `{category+label → {value, type}}` for every field the filler touched.

**Multi-step forms — solved by driving, not detecting (per founder):** the filler **auto-advances through ALL intermediate steps itself** (clicks every "Next"), and stops only at the **final page** to hand off in `awaiting_review`. So the only button the user ever clicks is the real **Submit** — no ambiguity about which button is final.
- **In-scope requirement:** the filler must distinguish, *on the current page*, a **Submit button from a Next button** (so it knows where to stop advancing). This is the same button-matching the filler already does — NOT the harder "identify the final step among many."

**Snapshot #2 trigger — key on the Submit CLICK, not the native `submit` event or navigation:**
- Many ATSes submit via button `onclick`/AJAX with no native `<form>` submit → a `submit` listener alone misses them.
- SPA ATSes (Ashby) swap to confirmation in-place, no navigation → the click, not unload, is the reliable signal.
- Client-side validation can reject a submit (page stays) → snapshot on each attempt, **keep the last snapshot before a confirmed success.**
- Use a **capture-phase** listener (`addEventListener(..., true)`) so we read values synchronously *before* the site's own handler tears down the DOM.

**Diff computed server-side; send both snapshots raw.** Same moat logic as outcomes — capture finest grain, aggregate on read. A client-computed diff is lossy early-aggregation. Feeds "correction rate → zero" (fill accuracy = % fields submitted unedited).

**PII isolation (hard rule):** snapshot values are the most sensitive data in the system (name, visa, salary, essay text). A/B-only — **never crosses to C**. Tightest retention/consent of any data we hold.

**OPEN — entity home:** dedicated `field_corrections` table (clean separation, own PII retention, one row per review = both snapshots + derived diff) VS reuse `application_events` (cheaper, no new table, but mixes PII into the otherwise-aggregate-safe behavioral/D log). Founder lean pending. (Recorded lean: dedicated, for PII isolation.)

---

## Still to design (next sessions)

1. **Pipeline & entry points** — resolve main.py vs discovery_runner.py duplication.
3. **Contracts** — API↔extension (incl. queue endpoint → atomic claim, per lifecycle); (B/C/D) raw-event capture grain.
4. **Migration path** — ordered, safe steps from today's code to this target.

---

## Open threads to revisit

- Company discovery / Worker A / BuiltWith is broken — needs its own design pass.
- `config.py` still gpt-4o (deliberate — switching to Claude at tailoring time).
- `main.py process_single_job` tailoring commented out (deliberate — tailoring not built yet).
- Hard constraint: **July 27 tech-week pitch** (a demo + story, not a finished platform). July 15 launch is now flexible — architecture drives the date, not vice versa.
