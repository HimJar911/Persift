c# Persift — Target Architecture: Design Notes (COMPLETE — ready to promote)

> **Status: design COMPLETE (all sections locked through discussion, June 30 – July 1, 2026).** This is NOT the current architecture — it's the *target*, plus the migration path to reach it. Current state lives in CLAUDE.md / ARCHITECTURE.md / STATE.md. Next step: promote this to `TARGET_ARCHITECTURE.md` and execute the Migration path (bottom of file).
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
4. **Field Correction** — two-snapshot diff + dedicated `field_corrections` table (entity home). COMPLETE.
5. **Pipeline & entry points** — two-jobs reframe (live ingestion vs backlog banking), Flow A order (resolve→dedup, cheap pre-filter), narrow duplication extract, `discovery_staging`=banking-only. COMPLETE.
6. **Contracts** — API↔extension. 7-endpoint target table, queue→atomic-claim POST, `/failed` deleted as outcome-writer, fat `/submitted` carries snapshots, client reaping→server. COMPLETE.
7. **Migration path** — clean break, 9 ordered steps (schema→data→server→extension→delete), constraint widen/narrow two-step, gated deferrals. COMPLETE.

**DESIGN IS COMPLETE.** All sections locked. Next: promote to `TARGET_ARCHITECTURE.md` and execute Migration steps 1–4 (DB-only, safe) first. See "▶ DESIGN COMPLETE" at the bottom.
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
- *auto vs review* → **`submission_mode`** flag on the Application (`auto | review`; today's `notify_only` was a non-phase wearing a status — now CUT entirely, see Migration §)
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

**Entity home — LOCKED: dedicated `field_corrections` table.** One row per review = both snapshots (raw) + server-derived diff. Own retention/consent policy. Rationale: snapshots hold the most PII in the system (name, visa, salary, essay text); reusing `application_events` (the aggregate-safe D log) would pour crown-jewel PII into the one table meant to stay clean enough to aggregate/share — directly breaking the A/B-vs-C/D wall the rest of the architecture rests on. The cost is one migration (trivial at 1 user). **This table is A/B-only — never crosses to C.**

---

## Pipeline & entry points — LOCKED

**The reframe that unlocked this: `main.py` and `discovery_runner.py` are NOT the same pipeline duplicated — they are two genuinely different jobs.** Earlier framing ("the duplication is the bug") was wrong.

- **Live ingestion** (`main.py`): resolve a Jobright job's true identity *now* → promote to `jobs` → matcher → extension applies. Real-time, small volume. (The Slack write in `process_single_job` is a **placeholder for the extension handoff**, not a bug — it stands in until the extension is the consumer.)
- **Backlog banking** (`discovery_runner.py` on Render): Jobright's DB ≫ ours. Can't resolve now (BuiltWith costs money; Worker A was the cheap substitute and it didn't work → disabled). So **accumulate raw unresolved Jobright jobs into `discovery_staging` now**, resolve the whole backlog in ONE bulk pass the day BuiltWith is affordable. Deferred, large volume.

Because they want different things (resolve-immediately vs. bank-for-later), their `run_jobright_cycle` implementations *should* differ. Do NOT force them to share one cycle.

**Three problems this section addresses (renumbered from the tangle):**
1. **Flow A exists in neither file** (correctness bug). `main.py` resolves then Slack-notifies (data evaporates, nothing lands in `jobs`); `discovery_runner` banks raw and stops (no resolve/dedup/promote, Worker A off). The live ingestion pipeline is missing its middle. **This section builds it.**
2. **Narrow real duplication.** Only the truly-identical scaffolding is duplicated: the Jobright timestamp helpers (`_load_jobright_timestamp`/`_save_jobright_timestamp`, verbatim) and the `poll_jobright` call. **Extract these to a shared module.** The cycle logic around them legitimately differs — keep separate.
3. **`discovery_staging` overload** was Worker A (company discovery) writing there alongside job-banking. With Worker A dead and its own design pass pending, in the target `discovery_staging` belongs to the **banking pipeline alone** (holding tank for unresolved Jobright jobs). Company discovery gets its own home when that pass happens.

### Live-ingestion Flow A — the order (LOCKED)

```
poll → seniority filter
     → cheap pre-filter on Jobright provenance (drop Jobright ids already resolved before)
     → resolve apply URL (get TRUE identity: real ATS + native id)
     → dedup vs jobs on TRUE identity (new → promote; existing → append discovery source, no new row)
     → matcher picks up
```

**Two rulings locked:**
- **Resolve BEFORE the true-identity dedup**, not after. You only know the true identity after resolving, and dedup must be against the *true* identity so two Jobright postings of one real role collapse to a single `jobs` row (append to sources list — per Job-entity "Dedup"). Today's `main.py` dedups first on the *Jobright* id then resolves — backwards for the new model.
- **Cheap Jobright-id pre-filter in front of resolve** (cost guard). Resolution is the expensive step (HTTP now, BuiltWith later) and Jobright re-serves the same postings every poll. Cache the Jobright→true-id mapping and skip re-resolving known Jobright ids. Does NOT violate "resolve then insert" (nothing enters `jobs` pre-resolution) — it's a provenance pre-filter, not an identity dedup. Reuses existing `seen_ids`/`poller_state` machinery.

**Deferred to the BuiltWith pass (intent locked, mechanics later):** the bulk-resolve job that drains the `discovery_staging` backlog through the same resolve→dedup→promote steps once BuiltWith lands.

**Entry-point shape:** shared scaffolding module (Jobright helpers + poll) imported by both; each entry point keeps its own thin cycle + scheduler wiring. Deploy-target question (Render-dies-with-AWS vs. two-targets-forever) deferred — the shared-core shape is correct either way and doesn't depend on it.

---

## Contracts — API↔extension (LOCKED)

Read against today's code (`api/server.py`, `extension/api.js`, `extension/background.js`, June 30). The lifecycle rename ripples into every endpoint; the atomic-claim ripple (lifecycle §Mechanism 1) reshapes the queue endpoint from a read into a write.

### Target endpoint table

| Endpoint | Method | Lifecycle effect | Outcome effect | Extension caller |
|---|---|---|---|---|
| `POST /jobs/claim` | **POST** (was `GET /jobs/queue`) | atomic `ready → submitting`, stamp `lease_expires_at`, `RETURNING` the job | — | `fetchNextJob` → becomes a claim |
| `GET /jobs/queue/count` | GET | counts `ready` (was `applying`) | — | `getQueueCount` |
| `POST /jobs/{id}/heartbeat` | POST | `submitting → submitting`, renew lease (`lease_expires_at = NOW()+10min`) | — | new `heartbeat` (formalizes today's in-memory `phase_started_at` bump) |
| `POST /jobs/{id}/submitted` | POST | `submitting → submitted` OR `awaiting_review → submitted`. **Fat endpoint:** body carries optional `{snapshots:[#1,#2]}` when review was on | writes **`applied_confirmed`** ONLY (source `extension_detected`, conf 1.0) | `markApplied` → renamed `markSubmitted` |
| `POST /jobs/{id}/awaiting_review` | POST | `submitting → awaiting_review` (fill done, auto-submit OFF) | — | `markNeedsReview` → renamed |
| `POST /jobs/{id}/released` | POST | `submitting → ready` (client voluntarily gives up a claim it can't finish; increments `retry_count`, respects cap). NOT abandon. | — | replaces client-side `markFailed('user_skipped'/'stale_timeout')` |
| `GET /jobs/{id}/resume` | GET | requires status `ready` OR `submitting` (was `applying`) | — | `getResumePdf` |

### The five breaks (all locked)

1. **Queue GET → atomic claim POST.** `GET /jobs/queue` (SELECT `applying`) had a read-then-act gap → double-apply. Now `POST /jobs/claim` = one-statement `UPDATE user_jobs SET status='submitting', lease_expires_at=NOW()+'10 min' WHERE id=(SELECT id ... WHERE status='ready' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING ...`. DB is the single arbiter. Extension's `fetchNextJob` stops being a passive read.

2. **Status strings rename everywhere** (server SQL + extension phase names): `applying` → `ready` (queue source) + `submitting` (claimed); `applied` → `submitted`; `needs_review` → `awaiting_review`; `failed`/`failed_stale`/`expired` → `abandoned` + `failure_reason`.

3. **`/failed` DELETED as an outcome-writer (bug #3 fix).** Today's `mark_failed` inserts `application_outcomes` `outcome_type='rejected'` for EVERY failure incl. `user_skipped`/crash → poisons the moat. Per source→type constraint, `extension_detected` may write ONLY `applied_confirmed`. Mechanical/user non-completion is a **lifecycle** event (`abandoned` + `failure_reason`), never an outcome. The old `/failed` endpoint's job splits into: `/released` (client gives up, retryable) and server-side cleanup (`submitting → abandoned` on lease expiry). No extension endpoint writes `abandoned` directly.

4. **`awaiting_review` gets an exit.** Old `needs_review` was a dead-end. Now `awaiting_review → submitted` via the fat `/submitted` endpoint, which ALSO carries the two Field-Correction snapshots.

5. **Client-side reaping → server-side.** Today `checkStale` in `background.js` calls `markFailed('stale_timeout')` — client declares itself dead. Per lifecycle §Mechanism 2, `submitting → abandoned` is written by **cleanup ONLY** (server lease-expiry sweep). Client only heartbeats; it never self-abandons. If the client knows it's giving up cleanly, it calls `/released` (→ `ready`, not `abandoned`).

### Fat-endpoint decision (LOCKED)

Snapshots ride on `POST /jobs/{id}/submitted` — NOT a separate `/corrections` endpoint. Submit is ONE real-world event; splitting lifecycle-write from correction-write invites half-recorded state (submitted but corrections lost, or vice versa). Server does the `field_corrections` insert + `user_jobs` status update **in one transaction**. Snapshots are optional in the body (present only when review was on / auto-submit off).

### Ripple carried forward
- `background.js` phase names (`idle|fetching|tab_open|filling|post_submit_wait`) are the CLIENT's own state machine and stay client-side, but the messages that hit the API (`success`/`failed`/`needs_review`/`heartbeat`) remap to the new endpoints above. `skip` and `stale_timeout` stop calling `markFailed`; they call `/released`.
- Migration section must sequence the rename so server + extension flip together (or the API accepts both old+new transiently). Carry to Migration.

---

## Migration path — clean break (LOCKED)

**Style: clean break** (chosen given 1 user / ~18K jobs / extension not shipped / no external consumers). Rename in place, drop old outright, no dual-support shim. The "server+extension must flip together" worry from Contracts **evaporates** — you own both and there's no live traffic. The only real ordering constraint is **schema-before-code**: a change can't land until what it depends on exists, and can't break a consumer not yet updated.

**Dependency spine:** schema → data rewrite → server code → extension code → delete old.

### Ground truth (DB inspected July 1, 2026 — 1 user, backup taken)
- **Migration-006 columns on `users` are ALL EMPTY** (`requires_sponsorship`, `work_auth_type`, `university`, `major`, `graduation_date`, `available_start_date`, `cohort_signup_week`). All real profile data lives in `application_settings` JSONB (28 keys). The dual-home bug is DORMANT (columns exist but unpopulated), so field-home migration is conflict-free: move JSONB→column, delete JSONB key, no reconciliation of competing values.
- **Naming reconciliations LOCKED:** (a) rename empty col `requires_sponsorship` → `needs_sponsorship` (matches JSONB + design) incl. its index; (b) add `visa_type` column (populate from JSONB), **DROP** the dead empty `work_auth_type` col + its CHECK (unused third vocabulary). Populated JSONB names win; empty 006 artifacts that were never used get dropped.

### Ordered steps

1. **Schema — additive first (nothing reads these yet).**
   - Add to `user_jobs`: `lease_expires_at TIMESTAMPTZ`. **(Confirmed present July 1: `failure_reason`, `submission_mode`, `current_stage`, `current_stage_entered_at`, `latest_outcome_id`, `retry_count`. Only `lease_expires_at` is genuinely new.)**
   - **`submission_mode` values → `auto | review`** (replace existing CHECK `review_before_submit|autonomous`). **`notify_only` CUT ENTIRELY** — notifying "a job exists" has no value (job boards do it free) and opts the user out of apply-through + outcome capture, the whole product. It was already vestigial (not in the current mode CHECK; only a zero-row leftover in the old status CHECK). If a notify tier ever becomes real, re-add one CHECK value then — don't carry a dead branch through every state machine now.
   - New table `field_corrections` (one row/review: `user_job_id`, `snapshot_filled JSONB`, `snapshot_submitted JSONB`, `diff JSONB`, timestamps). A/B-only, own retention.
   - Add source→type CHECK on `application_outcomes`: `extension_detected` ⇒ `outcome_type='applied_confirmed'` only.

1b. **Field homes — JSONB → columns (the founding-bug fix; conflict-free per Ground Truth).**
   - Add columns: `gpa`, `visa_type`, `location_city`, `location_state`, `location_preference` (local|remote|anywhere — NEW, no data yet).
   - Rename `requires_sponsorship` → `needs_sponsorship` (+ index `idx_users_requires_sponsorship` → `idx_users_needs_sponsorship`).
   - **Data move:** copy JSONB `school`→`university`, `major`→`major`, `gpa`→`gpa`, `graduation_date`→`graduation_date`, `needs_sponsorship`→`needs_sponsorship`, `visa_type`→`visa_type`, `location_city/state`→cols; then **remove those keys from `application_settings`** so each fact has ONE home.
   - **`graduation_date` storage LOCKED: canonical `date` column, coerce free-text.** JSONB held `"May 2027"` (month+year, no day). Rule: **store canonical (structured date, e.g. `2027-05-01`), render per-form at fill time.** From a date the filler can emit any format a form wants (calendar `05/01/2027`, free-text `May 2027`, split month/year dropdowns); the reverse (free-text→date) is an unreliable guess and would break calendar-day forms. The invented day (1st) is a harmless anchor — never surfaced (filler renders month+year for display). Parse any future free-text grad date to a canonical date on ingest.
   - **Drop** dead `work_auth_type` col + `users_work_auth_type_check`.
   - JSONB KEEPS (form-fill carry-along, never queried): `eeo_*`, `linkedin_url`, `github_url`, `preferred_name`, `previous_employers`, `phone`, `first_name`, `last_name`, `email`(also col), `degree`, `location_country`, `work_authorized`, compensation fallback, `custom_answers` (until LLM free-text lands). `desired_hourly_*`/`desired_salary_*` → per-design computed-per-job; leave as JSONB fallback for now.

2. **Status CHECK constraint — WIDEN (the one unavoidable two-step).** A CHECK can't be renamed, only replaced, and can't forbid a value that rows still hold. So: replace `user_jobs_status_check` with one allowing **old + new** names transiently (`applying, applied, needs_review, failed, failed_stale, expired` AND `matched, preparing, ready, submitting, awaiting_review, submitted, abandoned`).

3. **Data rewrite (one-shot — CONFIRMED tiny: 4 rows, all `needs_review`, nothing mid-flight).** Map: `needs_review → awaiting_review` (the only rows that exist); the other mappings (`queued→matched`, `applying→ready`, `applied→submitted`, `failed/failed_stale/expired→abandoned`) are defined for completeness but hit 0 rows today. **Delete any fake `rejected` outcomes** from `mark_failed` (bug #3 cleanup — verify count; likely 0 given no failed rows). Field-home JSONB→column data move (step 1b) runs in THIS transaction.

4. **Status CHECK constraint — NARROW.** Replace again to allow **new names only**. Old names now impossible to write.

5. **Server code.** Rewrite `api/server.py` endpoints to the target table (Contracts §): `GET /jobs/queue` → `POST /jobs/claim` (atomic `UPDATE...RETURNING FOR UPDATE SKIP LOCKED`); `/applied` → `/submitted` (fat, accepts snapshots, writes `field_corrections` + status in one txn); add `/heartbeat`, `/released`; `/needs_review` → `/awaiting_review`; **delete `/failed`'s outcome insert entirely**; `/resume` + `queue/count` read new statuses. Matcher/tailor_worker write new status names per lifecycle single-writer table.

6. **Server cleanup job (`run_cleanup_job` in main.py).** Replace the 48h/1h `expired`/`failed_stale` sweeps with ONE lease-expiry sweep: `submitting` with `lease_expires_at < NOW()` → `abandoned`. Add the `abandoned → ready` retry (respecting `retry_count` cap = 2). This is now the SOLE writer of `submitting → abandoned`.

7. **Extension code.** `api.js`: `fetchNextJob` → claim POST; `markApplied` → `markSubmitted` (sends snapshots when review-off); `markNeedsReview` → `markAwaitingReview`; rename/point `heartbeat`. `background.js`: `checkStale` stops calling `markFailed` — client no longer self-abandons; clean giveup (`skip`) calls `/released`, stale is left for server cleanup. Wire the two-snapshot capture (capture-phase Submit listener) — build later, but the endpoint accepts it now.

8. **Pipeline (Flow A + entry points, from Pipeline §).** Reorder Jobright cycle to resolve→dedup-on-true-identity, add cheap Jobright-id pre-filter, make `main.py`'s cycle promote to `jobs` (replace the Slack stub when extension is the consumer). Extract shared Jobright scaffolding to a module imported by both entry points. `discovery_staging` = banking-only.

9. **Delete old.** Remove dead statuses from any remaining references, drop the commented-out `process_single_job` full-pipeline block if superseded, retire `QUESTION_ALIASES`/`custom_answers` once LLM free-text lands (gated on Anthropic key — defer with L4).

### Sequencing notes
- Steps 1–4 are DB-only and safe to run before any code changes (additive, then a data rewrite while the constraint is wide).
- Steps 5–7 (server + extension) can flip in either order under clean-break since there's no live traffic, but do **server before extension** so you can smoke-test endpoints with curl before the extension depends on them.
- Steps 8–9 are independent of the status rename and can follow.
- **Gated-on-Anthropic-key (defer, same as L4):** LLM free-text answers, `custom_answers`/`QUESTION_ALIASES` removal.
- **Gated-on-BuiltWith (separate pass):** backlog bulk-resolve, company discovery / Worker A.

---

## ▶ DESIGN COMPLETE

All target-architecture sections are locked. Next step is to promote this file to `TARGET_ARCHITECTURE.md` and begin executing the Migration path above (steps 1–4 first — DB-only, safe, high-leverage at 1 user). Keep CLAUDE.md/ARCHITECTURE.md/STATE.md honest as each step lands.

---

## Open threads to revisit

- **Filler date-rendering helper (fill-time, lands with filler wiring):** given a stored canonical `date` + the detected field format (calendar / free-text / split dropdowns), output the right string. Belongs in `filler_utils`. Enables "store canonical, render per-form" for `graduation_date` (and any date field). Not part of the DB migration.
- Company discovery / Worker A / BuiltWith is broken — needs its own design pass.
- `config.py` still gpt-4o (deliberate — switching to Claude at tailoring time).
- `main.py process_single_job` tailoring commented out (deliberate — tailoring not built yet).
- Hard constraint: **July 27 tech-week pitch** (a demo + story, not a finished platform). July 15 launch is now flexible — architecture drives the date, not vice versa.
