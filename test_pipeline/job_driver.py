"""Single-job lifecycle: DB seed -> state reset -> trigger -> poll for
terminal state -> field verification -> debug log capture -> tab cleanup ->
state+log writes. Automates extension/TEST_COMMANDS.md exactly, per
joyful-sprouting-swan.md's "Per-job lifecycle" section.

Public API:
    run_job(worker_ctx, job) -> JobResult
"""

import asyncio
import dataclasses
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

import test_pipeline.db_state as db_state
from test_pipeline.circuit_breaker import looks_blocked
from test_pipeline.failure_log import FieldFailure, JobFailureRecord

logger = logging.getLogger(__name__)

# Real fills take seconds; the server's own 30-min REVIEW_TIMEOUT_MS is far
# too long to wait per-job at scale (per the plan's "Per-job lifecycle" §4).
_POLL_TIMEOUT_S = 90
_POLL_INTERVAL_S = 1.5

_DEBUG_LOG_DIR = Path(__file__).resolve().parent.parent / "failures" / "debug_logs"


@dataclasses.dataclass
class WorkerContext:
    """Everything a single worker coroutine needs to drive one job. One
    persistent Chrome context + its extension service worker + its own test
    user, per harness_runner.py's per-worker isolation design."""
    worker_id: int
    context: object          # playwright.async_api.BrowserContext (persistent)
    service_worker: object   # playwright.async_api.Worker
    user_id: str
    api_base_url: str
    run_id: int
    harness_version: str


@dataclasses.dataclass
class JobResult:
    job_id: str
    ats: str
    outcome: str
    phase_reached: str | None
    failure_reason: str | None
    fields_filled: int | None
    fields_total: int | None
    page_fingerprint: str | None
    debug_log_ref: str | None
    field_failures: list[FieldFailure]
    page_block_detected: bool = False
    page_block_reason: str | None = None
    all_attempts: list[dict] = dataclasses.field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 1: DB seed
# ---------------------------------------------------------------------------

async def _seed_user_job(user_id: str, job_id: str, ats: str) -> None:
    """INSERT (not UPDATE) — per the plan, this job was never in user_jobs
    for this test user. retry_count is reset to 0 every time so harness-level
    retries never trip the real _RETRY_CAP (api/server.py).

    Real bug found live (Aug 7 2026): a diagnostic script proved the
    extension's own claimNextJob() (POST /jobs/claim) is a COMPLETELY
    INDEPENDENT claim path from the harness's own job tracking — the
    extension polls the real, shared user_jobs queue for this test user,
    not "whatever job the harness just told it to do." /jobs/claim orders
    by created_at ASC (api/server.py), but this INSERT...ON CONFLICT DO
    UPDATE only ever refreshed updated_at, never created_at -- so a stale
    'ready' row left over from an EARLIER job this same test user was
    seeded for (e.g. one the harness force-released as a timeout before
    the extension got to it) sat at the front of the FIFO queue and got
    claimed first, ahead of the job the harness actually just seeded and
    was tracking. Confirmed live: 4 stale 'ready' rows had accumulated for
    one test user; this explained essentially the entire
    not_a_standard_greenhouse_form / needs_review_non_submit rate (~16-26%
    across several runs) -- the extension was checking a DIFFERENT job's
    page than what the harness thought it was checking, on every
    occurrence. Two earlier fix attempts (a form-render-timing wait, then
    closing all leaked tabs) both missed this because the tab/DOM they
    were looking at genuinely belonged to a different, real job -- there
    was nothing wrong with the DOM-detection logic itself.

    Fixed by clearing every other 'ready' row for this user before
    seeding the new one, so at any moment there is at most ONE row
    eligible for this user's claim, and it is unambiguously the one the
    harness is tracking."""
    pool = db_state.get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                UPDATE user_jobs
                SET status = 'abandoned', updated_at = NOW()
                WHERE user_id = $1::uuid AND status = 'ready'
                  AND NOT (job_id = $2 AND job_ats = $3)
                """,
                user_id, job_id, ats,
            )
            await conn.execute(
                """
                INSERT INTO user_jobs (user_id, job_id, job_ats, status, retry_count,
                                        current_stage, failure_reason, lease_expires_at, updated_at)
                VALUES ($1::uuid, $2, $3, 'ready', 0, NULL, NULL, NULL, NOW())
                ON CONFLICT (user_id, job_id, job_ats) DO UPDATE
                    SET status = 'ready', retry_count = 0, current_stage = NULL,
                        failure_reason = NULL, lease_expires_at = NULL, updated_at = NOW()
                """,
                user_id, job_id, ats,
            )


# ---------------------------------------------------------------------------
# Step 2-3: state reset + trigger
# ---------------------------------------------------------------------------

async def _reset_extension_state(sw, user_id: str) -> None:
    await sw.evaluate(
        """(userId) => new Promise(resolve => {
            chrome.storage.local.set({
                phase: 'idle', current_job: null, current_tab_id: null,
                phase_started_at: null, user_id: userId, debug_log: [],
            }, resolve);
        })""",
        user_id,
    )


async def _trigger_poll(sw) -> None:
    await sw.evaluate("() => runPollCycle()")


# ---------------------------------------------------------------------------
# Step 4: poll for terminal state
# ---------------------------------------------------------------------------

async def _read_storage(sw) -> dict:
    return await sw.evaluate(
        "() => new Promise(resolve => chrome.storage.local.get(null, resolve))"
    )


def _is_real_job_page(url: str) -> bool:
    """Excludes both extension pages and the browser's own placeholder tabs
    (about:blank, chrome://newtab/) — real bug found live: a fresh
    persistent context's default about:blank tab was being returned as if
    it were the job's real tab, because the original filter only excluded
    chrome-extension:// URLs. This produced a false 90s timeout on jobs
    that actually completed correctly in ~12s when re-run manually — the
    harness was polling chrome.storage.local (fine) but the block-check /
    field-verification / page-fingerprint logic downstream all silently
    operated on about:blank instead of the real tab."""
    if not url or url == "about:blank":
        return False
    if url.startswith("chrome-extension://") or url.startswith("chrome://"):
        return False
    return True


async def _poll_until_tab_open(sw, context, timeout_s: float = 20.0):
    """Waits for phase to leave 'fetching'/'idle' and a REAL (non-blank,
    non-extension) page to appear in the context — the earliest point a
    block-signature check can run, per the plan's "checked right after
    each tab opens, before the extension starts filling." Returns the
    Page, or None if no real tab ever opened within timeout_s (e.g. the
    claim itself returned no job)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        candidates = [p for p in context.pages if _is_real_job_page(p.url)]
        if candidates:
            return candidates[-1]
        await asyncio.sleep(0.5)
    return None


async def _poll_for_terminal(sw, timeout_s: float = _POLL_TIMEOUT_S) -> tuple[str, dict]:
    """Returns (outcome, final_storage_snapshot). outcome is one of
    'mechanically_verified' (provisional — field verification confirms),
    'needs_review_non_submit', 'failed', 'timeout'."""
    deadline = time.monotonic() + timeout_s
    started_idle_departure_seen = False

    while time.monotonic() < deadline:
        storage = await _read_storage(sw)
        phase = storage.get("phase")

        if phase != "idle":
            started_idle_departure_seen = True

        if phase == "awaiting_review":
            reason = (storage.get("pending_review") or {}).get("reason")
            if reason == "awaiting_user_submit":
                return "mechanically_verified", storage
            return "needs_review_non_submit", storage

        if phase == "idle" and started_idle_departure_seen:
            # background.js's case 'failed' resets to idle (see
            # extension/background.js:356-367) — this is the only way idle
            # is re-observed after having left it.
            return "failed", storage

        await asyncio.sleep(_POLL_INTERVAL_S)

    return "timeout", await _read_storage(sw)


async def _force_release(api_base_url: str, user_id: str, job_id: str, ats: str) -> None:
    """On harness-side timeout, force-release directly via the API rather
    than waiting on the server's own 30-min lease-expiry sweep."""
    async with httpx.AsyncClient(base_url=api_base_url, timeout=15.0) as client:
        try:
            resp = await client.post(
                f"/jobs/{job_id}/released",
                json={"user_id": user_id, "job_ats": ats, "reason": "harness_timeout"},
            )
            if resp.status_code not in (200, 404):
                logger.warning("Force-release non-2xx for job %s: %s %s", job_id, resp.status_code, resp.text)
        except Exception:
            logger.warning("Force-release failed for job %s", job_id, exc_info=True)


# ---------------------------------------------------------------------------
# Step 5: independent field verification
# ---------------------------------------------------------------------------

# Deliberately independent of filler_utils.js's enrichField()/collectFields()
# — per the plan, reusing the code under test to verify the code under test
# can't catch that code's own blind spots (same reasoning as
# corpus_harvester.py's independent extraction JS). The extension is never
# modified to expose harness-only hooks (the plan is explicit: "extension/ is
# never modified by the harness"), so this can't rely on a bespoke global —
# instead it parses the real, already-existing per-field log line every fill
# attempt already produces (filler_utils.js's runPass(), e.g.
# "filler: filled (verified) — email | Email Address" or
# "filler: fill failed [reason] — phone | Phone"), which reaches
# chrome.storage.local's debug_log via the console.log relay in
# extension/content/greenhouse.js. It then independently re-scans the live
# DOM for a field whose label text matches, and checks ITS OWN read of the
# current value/selection — not the log line's self-reported verdict — so a
# misclassified-but-plausible fill can still be caught if the true landed
# value is empty (see decisions/0010: this still can't tell right from
# plausible-looking, only landed from empty).
_ATTEMPT_LINE_RE = (
    r"^filler: (filled \(verified\)|filled \(unverified\)|fill failed)"
    r"(?: \[([^\]]*)\])? — ([^|]+) \| (.+)$"
)

_FIND_BY_LABEL_JS = r"""
(labelText) => {
    // labelText arrives already truncated to 60 chars by the debug_log line
    // filler_utils.js itself produced (field.label.slice(0, 60)). Matching
    // via startsWith on a re-trimmed, re-sliced-then-trimmed DOM label,
    // rather than exact equality on two independently-truncated strings, is
    // required — a real bug found live: the 60-char cut can land mid-word
    // right before a trailing space, and trimming AFTER vs BEFORE that cut
    // (as filler_utils.js's log line vs. this independent DOM read do,
    // respectively) produces two strings that differ by exactly that
    // trailing space, so exact-equality false-negatived on a field that was
    // actually correctly filled (needs_sponsorship, Apexcompanies job
    // 5113246008, confirmed live). A prefix match, both sides trimmed after
    // slicing, is robust to that boundary difference.
    //
    // Second real bug found live (Oklo job 5743023004, "Are you legally
    // authorized to work in the United States?"): filler_utils.js's
    // getLabelForEl() reads via .innerText (rendered text, collapses
    // line-break whitespace to a space) and checks aria-labelledby BEFORE
    // el.labels — this independent re-check used el.labels only (which is
    // empty for aria-labelledby-associated inputs, a real and common
    // Greenhouse pattern) and .textContent (raw DOM text, preserves a
    // literal "\n" between the question and a trailing "*"). Both gaps
    // together produced a false MISS on a field that was actually
    // correctly filled. Fixed: check aria-labelledby first (same priority
    // order as getLabelForEl), and collapse all internal whitespace runs
    // to a single space before comparing, not just trim the ends.
    const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase().slice(0, 60).trim();
    const target = norm(labelText);
    const candidates = document.querySelectorAll('input, select, textarea, [role="combobox"]');
    for (const el of candidates) {
        let rawText = '';
        const labelledBy = el.getAttribute('aria-labelledby');
        if (labelledBy) {
            rawText = labelledBy.split(' ')
                .map(id => { const e = document.getElementById(id); return e ? e.innerText : ''; })
                .filter(Boolean)
                .join(' ');
        }
        if (!rawText) {
            const labelEl = el.labels && el.labels[0];
            rawText = labelEl ? labelEl.innerText : (el.getAttribute('aria-label') || el.placeholder || '');
        }
        const text = norm(rawText);
        if (text && (text === target || text.startsWith(target) || target.startsWith(text))) {
            let value = '';
            let role = el.getAttribute('role') || '';
            if (el.tagName === 'SELECT') {
                value = el.options[el.selectedIndex] ? el.options[el.selectedIndex].text : '';
            } else if (el.type === 'checkbox' || el.type === 'radio') {
                value = el.checked ? 'checked' : '';
            } else {
                value = el.value || '';
                if (!value) {
                    const control = el.closest('.select__control');
                    const sv = control ? control.querySelector('.select__single-value') : null;
                    value = sv ? sv.textContent : '';
                    if (control) role = role || 'combobox';
                }
            }
            // Structural signals mirroring filler_utils.js's enrichField(),
            // captured independently here (not reused from the extension)
            // so cluster.py's structural-fingerprint grouping has real data
            // to key on for BOTH failures and successes, not just label
            // text — per the plan's clustering spec (autocomplete/id/role/
            // html_type/options_hash, checked before label similarity).
            let optionsHash = '';
            try {
                let optionTexts = [];
                if (el.tagName === 'SELECT') {
                    optionTexts = Array.from(el.options).map(o => o.text.trim());
                } else {
                    const control = el.closest('.select__control');
                    if (control) {
                        // Options only populate once opened — best-effort only,
                        // same known limitation as enrichField()'s options field.
                        optionTexts = [];
                    }
                }
                if (optionTexts.length) {
                    let hash = 0;
                    const joined = optionTexts.join('|');
                    for (let i = 0; i < joined.length; i++) {
                        hash = ((hash << 5) - hash + joined.charCodeAt(i)) | 0;
                    }
                    optionsHash = hash.toString(16);
                }
            } catch (e) { /* best-effort only */ }

            return {
                found: true,
                landed: !!value && value.trim().length > 0,
                autocomplete: el.getAttribute('autocomplete') || '',
                id: el.id || '',
                role: role,
                html_type: el.type || el.tagName.toLowerCase(),
                options_hash: optionsHash,
                required: !!el.required,
            };
        }
    }
    return { found: false, landed: false };
}
"""


def _parse_attempt_lines(debug_log: list) -> list[dict]:
    import re
    pattern = re.compile(_ATTEMPT_LINE_RE)
    attempts = []
    for entry in debug_log:
        text = entry.get("text", "") if isinstance(entry, dict) else str(entry)
        m = pattern.match(text)
        if not m:
            continue
        outcome_phrase, reason, category, label = m.groups()
        attempts.append({
            "self_reported_verified": outcome_phrase == "filled (verified)",
            "reason": reason,
            "category": category.strip(),
            "label": label.strip(),
        })
    return attempts


def _pick_verification_frame(page):
    """Real gap found live (Aug 8 2026, after the manifest.json all_frames
    fix landed — STATE.md's timeout investigation): ~32% of the Greenhouse
    corpus is a company's own branded career page embedding the real
    Greenhouse form in an <iframe src="https://job-boards.greenhouse.io/
    embed/job_app?...">, not the top-level document. greenhouse.js now
    correctly runs inside that iframe (content_scripts' "all_frames": true),
    fills real fields, and self-reports success — but page.evaluate() on a
    bare Playwright Page always targets the MAIN frame only, so this
    independent verification was silently checking the wrong document and
    misreporting every real branded-domain success as
    VERIFICATION_LANDED_EMPTY. Prefer a job-boards.greenhouse.io frame if one
    exists (the iframe case); otherwise fall back to the main frame
    (the ordinary standalone-Greenhouse-page case, where page itself IS
    that frame)."""
    for frame in page.frames:
        if "job-boards.greenhouse.io" in frame.url:
            return frame
    return page.main_frame


async def _verify_fields(page, debug_log: list) -> tuple[int, int, list[dict], list[dict]]:
    """Returns (fields_filled, fields_total, landed_empty_gaps, all_attempts).

    all_attempts carries every field the extension's logs claim it
    attempted, enriched with the harness's own independently-read structural
    signals (autocomplete/id/role/html_type/options_hash) and landed-value
    verdict — for BOTH successful and failed fields. This is the real data
    source cluster.py's structural-fingerprint grouping and paired-success
    lookup need; earlier drafts of this module only captured structure for
    failures, which left cluster.py with nothing to diff a failing field's
    structure against (the plan explicitly wants "800 React-Select
    comboboxes succeed, 20 fail — what do those 20 share that the 800
    don't," which is impossible without structural data on the 800 too)."""
    attempts = _parse_attempt_lines(debug_log)
    if not attempts:
        return 0, 0, [], []

    frame = _pick_verification_frame(page)
    landed_empty = []
    all_attempts = []
    filled_count = 0
    for a in attempts:
        try:
            result = await frame.evaluate(_FIND_BY_LABEL_JS, a["label"])
        except Exception:
            result = {"found": False, "landed": False}

        landed = bool(result.get("landed"))
        enriched = {
            **a,
            "landed": landed,
            "autocomplete": result.get("autocomplete", ""),
            "id": result.get("id", ""),
            "role": result.get("role", ""),
            "html_type": result.get("html_type", ""),
            "options_hash": result.get("options_hash", ""),
            "required": bool(result.get("required", False)),
        }
        all_attempts.append(enriched)

        if landed:
            filled_count += 1
        elif a["self_reported_verified"]:
            # The extension logged success but the harness's own independent
            # DOM read disagrees — a real "verification gap" class, distinct
            # from a plain fill failure the extension already knew about.
            landed_empty.append({**enriched, "reason_code": "VERIFICATION_LANDED_EMPTY"})

    return filled_count, len(attempts), landed_empty, all_attempts


# ---------------------------------------------------------------------------
# Step 6: debug log capture
# ---------------------------------------------------------------------------

def _save_debug_log(run_id: int, job_id: str, debug_log: list) -> str:
    out_dir = _DEBUG_LOG_DIR / str(run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{job_id}.json"
    out_path.write_text(json.dumps(debug_log, indent=2), encoding="utf-8")
    return str(out_path.relative_to(_DEBUG_LOG_DIR.parent.parent))


# ---------------------------------------------------------------------------
# Page fingerprint (structural, DOM-level — see plan's "page-layout
# diversity" blind-spot section)
# ---------------------------------------------------------------------------

_FINGERPRINT_JS = r"""
() => {
    const classNames = new Set();
    document.querySelectorAll('[class]').forEach(el => {
        el.className.toString().split(/\s+/).forEach(c => {
            if (c) classNames.add(c.replace(/[0-9a-f]{6,}/gi, ''));
        });
    });
    const hasIframe = document.querySelectorAll('iframe').length > 0;
    const hasEmbedScript = !!document.querySelector('script[src*="embed"]');
    const sortedClasses = Array.from(classNames).sort().join(',');
    return { sortedClasses, hasIframe, hasEmbedScript };
}
"""


async def _compute_page_fingerprint(page) -> str:
    try:
        info = await page.evaluate(_FINGERPRINT_JS)
    except Exception:
        return "unknown"
    raw = f"{info['sortedClasses']}|iframe={info['hasIframe']}|embed={info['hasEmbedScript']}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

async def run_job(ctx: WorkerContext, job: dict) -> JobResult:
    """job = {'job_id': ..., 'ats': ..., 'sample_phase': ...} from
    db_state.claim_next_pending(). Never clicks submit — fill+verify only."""
    job_id, ats = job["job_id"], job["ats"]
    page = None
    field_failures: list[FieldFailure] = []
    debug_log_ref = None
    page_fingerprint = None
    fields_filled = fields_total = None
    page_block_detected = False
    page_block_reason = None
    all_attempts: list[dict] = []

    try:
        await _seed_user_job(ctx.user_id, job_id, ats)
        await _reset_extension_state(ctx.service_worker, ctx.user_id)
        await _trigger_poll(ctx.service_worker)

        # Block-signature check "right after each tab opens, before the
        # extension starts filling" (per the plan's Circuit Breaker section)
        # — this is the earliest point a Page object exists to check at all,
        # so it has to happen here in job_driver.py, not in the outer runner
        # loop which only sees the job after it's already finished.
        early_page = await _poll_until_tab_open(ctx.service_worker, ctx.context)
        if early_page is not None:
            try:
                await early_page.wait_for_load_state("domcontentloaded", timeout=15_000)
                html = await early_page.content()
                # looks_blocked's status-based fast-path (403/429) needs the
                # REAL HTTP status of the page — this was a live bug: the
                # tab was discovered via _poll_until_tab_open (an
                # already-navigated Page from context.pages, not our own
                # goto()), so there was no Response object in scope and the
                # call site passed status=None unconditionally, silently
                # disabling the 403/429 fast-path entirely. A Cloudflare
                # 403 block was misclassified as a plain 'timeout' instead
                # of 'skipped_blocked' (confirmed live: the Bayada cluster
                # that tripped Phase 2's circuit breaker on an outcome
                # streak was actually 403-blocked, not organically slow).
                # An independent httpx HEAD to the same URL recovers the
                # real status without re-navigating the page Playwright is
                # already tracking.
                status = None
                try:
                    async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                        status_resp = await client.head(early_page.url)
                        status = status_resp.status_code
                except Exception:
                    logger.warning("Status check failed for job %s — falling back to regex-only block detection",
                                   job_id, exc_info=True)
                if looks_blocked(html, status):
                    page_block_detected = True
                    page_block_reason = "block signature detected on initial tab load"
                    logger.warning("Page block signature detected for job %s (status=%s)", job_id, status)
            except Exception:
                logger.warning("Block-check failed to read page content for job %s", job_id, exc_info=True)

        outcome, storage = await _poll_for_terminal(ctx.service_worker)
        phase_reached = storage.get("phase")
        failure_reason = None
        if outcome == "failed":
            # background.js's 'failed' handler resets current_job/pending_review
            # to null before this poll observes idle (see resetToIdle() at
            # background.js:356-367) — the real reason string content.js's
            # send({type:'failed', reason:...}) carried is never persisted to
            # chrome.storage.local at all, only relayed transiently over
            # chrome.runtime.sendMessage. It's genuinely not recoverable from
            # storage; the debug_log's last lines (already saved via
            # debug_log_ref below) are the real diagnostic trail for this
            # case, not this field. Named honestly rather than a bare
            # "unknown" with no indication why it's unknown.
            failure_reason = (storage.get("pending_review") or {}).get("reason") \
                or "not_recoverable_from_storage_see_debug_log"
        elif outcome == "needs_review_non_submit":
            failure_reason = (storage.get("pending_review") or {}).get("reason")
        elif outcome == "timeout":
            failure_reason = f"harness_timeout_after_{_POLL_TIMEOUT_S}s"
            await _force_release(ctx.api_base_url, ctx.user_id, job_id, ats)

        # The job's tab: each worker context runs exactly one job at a time
        # (one persistent context per worker, per harness_runner.py's
        # per-worker isolation), so the most-recently-opened real (non-blank,
        # non-extension) page in this context is unambiguously the job's
        # tab. Playwright Page objects carry no Chrome-internal tab-id
        # property to match against storage['current_tab_id'] directly, so
        # recency is the only reliable signal here, not an id lookup. Uses
        # the same _is_real_job_page() filter as _poll_until_tab_open — see
        # its docstring for the real bug this guards against (a fresh
        # context's about:blank tab being mistaken for the job's real tab).
        candidate_pages = [p for p in ctx.context.pages if _is_real_job_page(p.url)]
        if candidate_pages:
            page = candidate_pages[-1]

        if page is not None:
            page_fingerprint = await _compute_page_fingerprint(page)
            debug_log = storage.get("debug_log", [])

            # Run field verification whenever there are attempt lines to
            # check, not only on outcome == 'mechanically_verified' — a
            # 'failed' job can still have partial attempts logged before
            # whatever killed it (e.g. resume upload succeeded, form fields
            # were filling, then a later field caused the failure). Without
            # this, every failed job silently loses all its structural field
            # data, leaving cluster.py nothing to cluster for the run's most
            # important outcome class.
            if debug_log:
                fields_filled, fields_total, landed_empty, all_attempts = await _verify_fields(page, debug_log)

                if outcome == "mechanically_verified" and landed_empty:
                    # A field the extension logged as verified lands empty
                    # under the harness's own independent DOM re-check — a
                    # distinct "verification failure" bug class per the
                    # plan (extension thought it succeeded but didn't).
                    outcome = "failed"
                    failure_reason = "VERIFICATION_LANDED_EMPTY"

                for gap in landed_empty:
                    field_failures.append(FieldFailure(
                        reason_code="VERIFICATION_LANDED_EMPTY",
                        category_attempted=gap.get("category"),
                        autocomplete=gap.get("autocomplete", ""),
                        id=gap.get("id", ""),
                        role=gap.get("role", ""),
                        html_type=gap.get("html_type", ""),
                        options_hash=gap.get("options_hash", ""),
                        label=gap.get("label", ""),
                        section="",
                        required=gap.get("required", False),
                    ))

                # Fields the extension itself already reported as a fill
                # failure (not the harness's own verification gap) — real
                # structural data now available via the same enrichment.
                if outcome != "mechanically_verified":
                    for a in all_attempts:
                        if not a["self_reported_verified"] and not a["landed"]:
                            field_failures.append(FieldFailure(
                                reason_code=a.get("reason") or "EXTENSION_REPORTED_FAILURE",
                                category_attempted=a.get("category"),
                                autocomplete=a.get("autocomplete", ""),
                                id=a.get("id", ""),
                                role=a.get("role", ""),
                                html_type=a.get("html_type", ""),
                                options_hash=a.get("options_hash", ""),
                                label=a.get("label", ""),
                                section="",
                                required=a.get("required", False),
                            ))

        if outcome != "mechanically_verified":
            debug_log = storage.get("debug_log", [])
            debug_log_ref = _save_debug_log(ctx.run_id, job_id, debug_log)

    finally:
        # Mandatory per the plan: background.js never auto-closes tabs
        # (closeTab() calls commented out at lines 89/363) — skipping this
        # leaks memory across ~1000 jobs, the single highest-risk mechanical
        # omission the plan calls out.
        #
        # Real bug found live (Aug 7 2026): closing only `page` (the single
        # most-recently-opened real tab, per the "recency is unambiguous"
        # comment above) left OLDER real tabs open whenever a job didn't
        # cleanly finish before the next one started (e.g. a harness-level
        # timeout — the harness's 90s ceiling is bookkeeping only, it never
        # touches the extension's tab or storage state, so a timed-out
        # job's tab and its content script just keep running). That
        # leftover tab's content script eventually fires its own delayed
        # 'ready' handshake and reads whatever current_job happens to be in
        # storage at that moment — which by then belongs to a LATER job.
        # Confirmed live via debug_log job_id mismatches: a debug log saved
        # under job N's job_id contained context data from job N-2,
        # explaining a real ~16-18% of needs_review_non_submit outcomes
        # (not_a_standard_greenhouse_form) that were actually the extension
        # checking a stale, wrong tab's DOM, not a rendering-timing issue
        # (a first fix attempt targeting timing had no effect — this is the
        # real cause). Close EVERY real tab, not just the one selected as
        # "the" job's tab, so nothing outlives this job.
        for p in list(ctx.context.pages):
            if _is_real_job_page(p.url):
                try:
                    await p.close()
                except Exception:
                    pass

    # A page-level block signature overrides whatever terminal outcome the
    # extension itself reported — if the tab we saw was a CAPTCHA/Cloudflare
    # challenge, "failed"/"needs_review_non_submit" would misattribute the
    # cause to the extension when it's really a bot-detection wall. Recorded
    # as skipped_blocked so it's excluded from real failure-class clustering.
    if page_block_detected:
        outcome = "skipped_blocked"
        failure_reason = page_block_reason

    await db_state.update_job_outcome(
        ctx.run_id, job_id, ats, outcome=outcome, phase_reached=phase_reached,
        failure_reason=failure_reason, fields_filled=fields_filled,
        fields_total=fields_total, page_fingerprint=page_fingerprint,
        debug_log_ref=debug_log_ref, harness_version=ctx.harness_version,
    )

    result = JobResult(
        job_id=job_id, ats=ats, outcome=outcome, phase_reached=phase_reached,
        failure_reason=failure_reason, fields_filled=fields_filled,
        fields_total=fields_total, page_fingerprint=page_fingerprint,
        debug_log_ref=debug_log_ref, field_failures=field_failures,
        page_block_detected=page_block_detected, page_block_reason=page_block_reason,
        all_attempts=all_attempts,
    )
    return result
