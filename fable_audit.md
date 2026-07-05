# Persift Full-Codebase Audit — July 4, 2026

> Audit-only pass over the entire repo (main.py, config.py, db.py, api/, pollers/, pipeline/, migrations/, extension/, discovery_runner.py, update_profile.py). No code was modified. Findings ranked at the end by (blast radius) × (likelihood at 100-user beta).

**TL;DR:** The target-arch lifecycle work (status spine, atomic claim, single-writer edges) is genuinely solid — the migration did what STATE.md says it did. But the audit found a more fundamental problem *upstream* of everything: **the data ingestion layer never persists enriched job data.** Jobs are written to the DB before enrichment, and the enriched output is discarded, so `jobs.description`, `jobs.company_name` (for Greenhouse/Lever/Ashby), and `jobs.apply_url` (for Jobright) are empty for every row ever inserted. The matcher, tailor, and extension all consume those empty fields. STATE.md's claim that `main.py --no-discover` populates descriptions is false — no code path writes `jobs.description` after insert. Second-worst: the extension's success detection can report fake submissions, which re-creates the exact data-poisoning class (bug #3) the whole redesign was built to eliminate.

---

## Area 1 — Ingestion: enrichment output is thrown away (P0, systemic)

**The flow:** `poll_*()` → `detect_new_jobs()` → `filter_new_ids()` + `mark_seen_batch()` (INSERT) → `process_single_job()` → `enrich()` → Slack. The INSERT happens *before* enrichment, and `enrich()`'s dict is only ever handed to Slack.

Concretely, `mark_seen_batch` (db.py:126) inserts `j.get("description_plain_text", "")` — but the only things in the repo that ever produce a `description_plain_text` key are `enricher.py:50` (output never persisted) and `workday.py:95` (hardcoded `""`). The pollers produce:

- Greenhouse: `description_html` → **inserted as `''`**
- Ashby/Lever: `description_plain` → **inserted as `''`**
- SmartRecruiters: hardcoded `description_html: ""` — the API doesn't even return one at list level
- Jobright: `description_html: ""` (JD fetched lazily elsewhere)

Same pattern for `company_name` (Greenhouse/Lever/Ashby pollers don't set it; `enrich()` derives it from the slug but that's never written) and — worst of all — **Jobright `apply_url`**: `run_jobright_cycle` (main.py:254-269) calls `detect_new_jobs` (which INSERTs with `apply_url=""`) *first*, then resolves apply URLs into the in-memory dicts, then throws them away. Every Jobright job in the DB has an empty apply URL forever (`ON CONFLICT DO NOTHING` means it's never repaired).

**Failure scenarios, all live today:**

1. Matcher scores `resume_text` vs `description=''` → cosine similarity of an empty string → below the 50 threshold → **zero matches ever created for the four direct-ATS platforms** (the only ATSes the extension can apply to). The matcher's Jobright lazy-JD fetch patches this for scoring only — and even there, the fetched JD is used for `jd_text_snapshot` but never written to `jobs.description`, so `tailor_worker._DETAIL_SQL` reads an empty JD and L3/L4 tailor against nothing.
2. If a match somehow reaches the extension: `/jobs/claim` returns `company_name=''` → `filler_utils.resolveValue('previously_employed')` (filler_utils.js:1000-1005) does `emp.toLowerCase().includes(companyName.toLowerCase())` — `.includes('')` is always **true**, so any user with any previous employer answers "Yes, I was previously employed by this company" on every form. A concrete wrong-answer-on-a-real-application bug caused by the empty-data cascade.
3. A claimed Jobright job with `apply_url=''` → `chrome.tabs.create({url:''})` → stuck in `tab_open` → 10-min stale reset locally, server row leaks until the 3 a.m. reap, gets retried into the same dead loop up to the cap.

**Fix size:** Moderate, not an architecture change — persist enriched jobs (enrich *before* `mark_seen_batch`, or UPDATE after), and write Jobright apply URLs back after resolution. Must be sequenced with the doc fix: STATE.md pending-work item 3 ("Run main.py --no-discover → populates job descriptions") is **doc drift stating a false remedy**, and the "known issue: all job descriptions empty (HIGH)" row misdiagnoses it as an operational gap rather than a code bug.

## Area 2 — Extension: fake successes and cross-job attribution (P0)

**2a. `detectSuccess` false positive (greenhouse.js:126-130).** `urlChanged = !location.href.includes('/application')`. Two of the three manifest match patterns (`boards.greenhouse.io/*/jobs/*`, `job-boards.greenhouse.io/*`) are URLs that *never* contain `/application`, so `detectSuccess()` returns true from page load. On the auto-submit path: click submit → `waitFor(detectSuccess, 10000)` returns true instantly — **even if the form had validation errors and nothing was submitted** → `success` → `/jobs/{id}/submitted` → status `submitted` + `applied_confirmed` outcome with confidence 1.0. This is bug #3 reborn: the DB constraint stops `extension_detected` from writing *rejections*, but a fabricated `applied_confirmed` is exactly as poisonous to the career-center outcome data, and nothing structural prevents it. Quick fix (capture baseline URL / check for form-error elements), but it needs a real e2e test to trust.

**2b. Messages not gated by sender tab (background.js:170-286).** Only `ready` checks `sender.tab.id === state.current_tab_id`. `success`, `failed`, `needs_review`, and `heartbeat` all act on whatever `state.current_job` is *now*. This was mostly harmless when content scripts exited immediately; the Jul 4 review→submit fix makes them **stay alive for 30 minutes**, and debug mode leaves tabs open. Concrete failure: job A parks in `awaiting_review`; user clicks "Give up" (released); extension claims job B; the still-alive tab-A script sees the user manually submit A → sends `success` → **job B is marked submitted** and B's claim evaporates while its form was never filled. Also: tab A's heartbeats renew job B's lease. Quick fix (thread `sender.tab.id` through the gate), but it's a required companion to the Jul 4 change — the fix as shipped widened this hole.

**2c. Silent `markSubmitted` failure → real-world double-apply.** Every function in `api.js` swallows errors and returns false; `background.js` ignores the return value. If `/submitted` fails (network blip, server restart), the extension advances to `post_submit_wait` while the server row stays `submitting` → nightly reap → `abandoned` → cleanup retry → `ready` → **the extension re-applies to a job the user already submitted**. The atomic claim closed the concurrent double-apply; this sequential one is still open. Needs a retry/ack policy on `/submitted` (at minimum, retry until acked before moving on).

**2d. Ashby review-path click listener is fragile.** `submitBtn.addEventListener('click', {once:true})` on a React SPA — a re-render replaces the button node, the user's click lands on a new node, detection never fires, 30-min timeout releases a job the user actually submitted → retry → duplicate application. Same family as 2c: `awaiting_review → submitted` currently hangs on one DOM node reference surviving 30 minutes.

## Area 3 — Lifecycle gaps the target arch missed (P1)

**3a. `preparing` has no recovery path — despite being designed for crash recovery.** ARCHITECTURE.md says `preparing` exists to distinguish "started and died" for crash recovery, but *nothing recovers it*: the cleanup job (main.py:282-335) touches only `submitting` and `abandoned`. If the tailor process dies hard (weasyprint segfault — already a known Windows crasher — or SIGKILL between claim and the except-block's DB write), rows sit in `preparing` forever, invisible to every query. Also reachable without a crash: `_CLAIM_SQL` flips rows to `preparing`, then `_DETAIL_SQL` joins `jobs` — any claimed row whose join misses is claimed-but-never-processed and never fails either. Quick fix: cleanup sweep `preparing` older than N minutes → back to `matched`.

**3b. Cleanup resurrects tailor-failed rows to the wrong state.** Tailor failure → `abandoned` (no artifact on disk). Nightly cleanup step 2 moves all under-cap `abandoned` → `ready` — whose contract is "artifact on disk." The extension then claims it and `/resume` silently serves `base_resume.pdf`. If the tailor failure was deterministic (bad JD, weasyprint issue), the row also never gets re-tailored — it just cycles as an untailored apply. Tailor-failed rows should go back to `matched`. Quick fix, but it's a status-edge change — new single writer for `abandoned → matched`.

**3c. Claim can succeed and then return `{job: null}`.** `/jobs/claim` (server.py:212-262) commits `ready → submitting` + lease in query one, then runs a *separate* detail query; if that returns no row (or throws), the extension sees "no job" while the row is leased. It leaks until the nightly reap. Low likelihood per-call, but at 100 users × a claim every 5 min it's a steady drip. Quick fix: one transaction, release on detail-miss.

**3d. Lease is 10 minutes; the reaper runs once a day at 03:00.** A dead `submitting` row is invisible to `/claim` and `/queue/count` for up to 24 h. With one user that's cosmetic; with 100 users each holding at most one claim, one crashed tab = that user's pipeline frozen for a day. Quick fix: run the lease sweep every few minutes (it's already written as a single idempotent UPDATE), keep the 90-day delete nightly.

## Area 4 — Matcher timing design is the scaling landmine (P1)

The 6-min hardcoded lookback (matcher.py:36) coupled to the 6-min APScheduler cadence is documented — but the *design* fails under exactly the conditions beta creates. Interval triggers with `max_instances=1` **skip** a run if the previous one is still going or the process was suspended (laptop sleep, deploy, event-loop stall). A skipped run's 6-minute window is never scanned — those jobs are silently unmatched forever, with no error and no backfill. At 100 users, scoring is `jobs × users` MiniLM inferences on CPU per cycle; cycle time exceeding 6 minutes stops being an edge case and becomes the steady state. The fix is architectural but small: replace "wall-clock lookback" with a durable watermark (`poller_state`-style `last_matched_at`, or a `jobs.matched_at IS NULL` scan) so missed cycles self-heal.

The Jobright watermark has a sharper version of the same bug: **`main.py` and `discovery_runner.py` both write the same `poller_state.cursor` row** — if both run against one DB, the Render runner advances the watermark and main.py's Jobright→jobs path silently skips everything the runner already saw (the runner only stages to `discovery_staging`, never to `jobs`).

## Area 5 — API security: no auth at all (P0 before beta, by design-gap not bug)

Beyond the documented DEBUG set (CORS `*`, localhost BASE_URL): there is **no authentication on any endpoint**. Anyone with a user UUID can read the full profile — email, phone, GPA, visa status, EEO answers (`GET /users/{id}`), claim and burn a user's whole queue (`POST /jobs/claim`), or mark jobs submitted. UUIDs leak easily (they sit in `chrome.storage.local` and are pasted into a popup text field).

Additionally `GET /users/{user_id}/documents/{doc_type}` does no DB check and builds a filesystem path from the raw `user_id` segment — with an encoded slash/backslash this is a path-traversal candidate on Windows; `/jobs/{id}/resume` is only protected incidentally by the `::uuid` cast (invalid input → unhandled 500). STATE.md already lists "cybersecurity review not done (HIGH)"; concretely, the missing piece is an auth token minted at signup and checked on every request — that's an architecture addition (touches server, api.js, popup onboarding), not a flag flip, so it needs to be scheduled, not just remembered.

## Area 6 — Product/data-integrity items

- **Rewriter fabricates metrics** (rewriter.py:62): the L4 prompt instructs the model to "add plausible metrics where context implies them ('large dataset' → '10M+ record dataset')" — i.e., invent numbers on a student's resume that gets submitted to real employers under their name. For a company whose pitch is *trustworthy outcome data*, this is a reputational landmine independent of any bug. One-line prompt change; decide it deliberately.
- **Slack is the only notification channel, and it's the operator's webhook.** `notified` status + `notify_excluded_company` send to the single global `SLACK_WEBHOOK_URL`. At 100 users, "notify the user about an excluded-company match" notifies *you*, not them. The `notified` terminal state is currently writing rows whose promised user-facing side effect can't reach users. Architecture gap for beta (email or dashboard needed).
- **Popup XSS**: `popup.js` interpolates `company_name`/`title` (ATS-controlled strings) into `innerHTML`. A malicious posting title with markup executes in the extension popup. Quick fix (`textContent`).
- **`update_profile.py`** — confirmed still writing `visa_type`/`needs_sponsorship` into JSONB (documented landmine; unchanged).

## Area 7 — Doc drift found (fix the docs)

| Doc claim | Reality |
|---|---|
| STATE.md: "Run `main.py --no-discover` → populates job descriptions" (listed twice, incl. pending-work #3) | No code path writes `jobs.description` post-insert; running it changes nothing (Area 1) |
| CLAUDE.md/STATE.md: `discovery_runner.py` = "jobright poll + Worker A"; STATE diagram shows Worker A every 90 min live on Render | discovery_runner.py:184 — Worker A **disabled** (OOM on 512 MB); runner only stages to `discovery_staging`, never inserts into `jobs` |
| ARCHITECTURE.md fill diagram: `content/{greenhouse,ashby}.js → delegates ALL field filling to filler_utils` | ashby.js is fully hand-rolled (correctly stated three lines later and in CLAUDE.md — the diagram is the misleading part) |
| ARCHITECTURE.md: "`preparing` exists solely for crash recovery" | The recovery half was never built (Area 3a) |

**Not deep-audited:** `landing-page/` (independent of backend, not deployed — matches known issue), `pollers/workday.py`/`custom.py` (deferred scope), `discover_companies.py` beyond structure, the bulk of `filler_utils.js` DOM mechanics (verified the resolveValue↔getProfile contract holds, including the string-`'true'` handling, which is correct).

---

## Prioritized list (blast radius × likelihood at 100-user beta)

1. **Ingestion never persists enriched data** (Area 1) — the product's core loop is a no-op for the 4 supported ATSes; 100% already happening; also poisons tailoring and form answers (`previously_employed`). Moderate fix.
2. **No API auth + CORS `*`** (Area 5) — full PII exposure and queue tampering for every beta user the day it ships; certain to be exposed at launch. Architecture addition; start now, don't leave in the flag-flip bucket.
3. **False `applied_confirmed` from `detectSuccess`** (Area 2a) — corrupts the outcome dataset that is the paid product, and tells students they applied when they didn't; very likely already firing on `job-boards.greenhouse.io` URLs. Quick fix + e2e test.
4. **Un-gated extension messages + silent `/submitted` failure → double-apply/wrong-job attribution** (2b, 2c) — duplicate real-world applications under users' names; likelihood rose sharply with the Jul 4 stay-alive change. Quick fixes, do together with #3 before the pending Chrome test.
5. **Matcher watermark design** (Area 4) — silent permanent match loss on any skipped cycle; near-certain at beta load. Small architectural change (durable watermark), best done before matching is real (i.e., after #1).
6. **Lifecycle leaks: `preparing` unrecoverable, wrong retry target, claim leak, daily-only reap** (Area 3) — each strands individual user_jobs; individually low-frequency, collectively a steady queue-rot at 100 users. All quick fixes; bundle into one cleanup-job revision.
7. **Rewriter metric fabrication** (Area 6) — zero-likelihood-of-bug, high-blast-radius-if-noticed; one-line change pending a product decision.
8. **Jobright dual-writer watermark, Slack-only notifications, popup XSS, `update_profile.py`, doc drift** — real but bounded; fix opportunistically, docs in the same commit as #1 per CLAUDE.md's keep-docs-honest rule.

---

**Process observation:** the target-arch migration was verified bottom-up (each endpoint curl-checked, each edge single-writer) and that layer *is* clean — but nothing ever validated the pipeline end-to-end with real data, which is why an empty-`description` column could sit under a fully-verified state machine. The Verkada e2e test in STATE.md's pending list is the right instinct; extend it to start from a poll, not from a hand-seeded `user_jobs` row.
