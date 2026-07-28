"""P1.2 corpus harvester — offline, read-only Playwright crawl of stored
Greenhouse job postings, for FORM_ENGINE_DESIGN.md §3.6a.

Per §3.6a's founding principle, this deliberately does NOT reuse
extension/filler_utils.js's enrichField()/collectFields(): that code encodes
assumptions from staring at 2-3 forms and would just reproduce the same blind
spots. The in-page extraction JS below (_EXTRACTION_JS) is new, independent
code, run via page.evaluate().

Requires Playwright's Chromium binary (`python -m playwright install
chromium`) in addition to `pip install playwright` — the pip package alone
does not ship the browser. Run under Python 3.12 (the project's actual
interpreter — `py -3.12`), not whatever `python`/`py` defaults to.

Usage:
    python -m pipeline.corpus_harvester                  # full run
    python -m pipeline.corpus_harvester --limit 5         # smoke test
    python -m pipeline.corpus_harvester --retry-errors    # only retry 'error' rows
"""

import argparse
import asyncio
import gzip
import hashlib
import json
import logging
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright, Page

from db import close_db, get_pool, init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("corpus-harvester")

HARVESTER_VERSION = "1.3.0"

PROJECT_DIR = Path(__file__).resolve().parent.parent
CORPUS_DIR = PROJECT_DIR / "corpus"
PAGES_DIR = CORPUS_DIR / "pages"
MANIFEST_PATH = CORPUS_DIR / "manifest.jsonl"

_GOTO_TIMEOUT_MS = 30_000
_DOM_STABILITY_QUIET_MS = 500
_DOM_STABILITY_MAX_WAIT_MS = 5_000
_JITTER_MIN_S = 3.0
_JITTER_MAX_S = 8.0

# Consecutive no_form_found/error/likely_blocked results this improbable in a
# row (across random Greenhouse tenants) implies we're being blocked, not
# hitting organically bad forms. Tune down if real data shows false trips.
# Raised from 8 (v1.0.0's sequential-only threshold) once concurrent workers
# were added: with N workers interleaving results from many different tenants,
# a real streak of N-ish organic failures back-to-back is unremarkable and
# must not be confused with an actual block signal.
_BLOCK_STREAK_THRESHOLD = 20

_DEFAULT_CONCURRENCY = 1

# Recommended concurrency observed live 2026-07-26 on this dev machine
# (~7.4GB total RAM, already under load from other apps): concurrency=7
# caused the shared Playwright Node.js driver subprocess to die outright
# twice within ~15 min each time (free memory measured at ~247MB during the
# second death) — a single shared driver process means one OOM-adjacent
# event takes down every worker simultaneously, not just one. concurrency=3
# is the recommended ceiling on memory-constrained machines; raise only if
# `Get-CimInstance Win32_OperatingSystem` shows several GB free headroom.

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_BLOCK_SIGNATURES = re.compile(
    r"checking your browser before accessing|attention required.{0,40}cloudflare|"
    r"unusual traffic from your computer network|"
    r"complete the security check to continue|"
    r"access denied\s*<|"
    r"you have been blocked|request blocked by administrative rules|"
    r"verify you are a human",
    re.IGNORECASE,
)

_APPLY_TEXT_RE = re.compile(r"apply", re.IGNORECASE)

_FAILURE_STATUSES = {
    "no_form_found", "apply_button_clicked_no_form",
    "shadow_dom_unhandled", "iframe_unhandled", "likely_blocked", "error",
}

# ---------------------------------------------------------------------------
# In-page JS — exhaustive field discovery, independent of filler_utils.js
# ---------------------------------------------------------------------------

_EXTRACTION_JS = r"""
() => {
  function isVisible(el) {
    if (!el) return false;
    if (el.offsetParent !== null) return true;
    const cs = window.getComputedStyle(el);
    return cs.position === 'fixed' && cs.display !== 'none' && cs.visibility !== 'hidden';
  }

  function isHidden(el) {
    let node = el;
    while (node && node !== document.body) {
      if (node.hidden) return true;
      if (node.getAttribute && node.getAttribute('aria-hidden') === 'true') return true;
      const cs = window.getComputedStyle(node);
      if (cs.display === 'none' || cs.visibility === 'hidden') return true;
      node = node.parentElement;
    }
    return false;
  }

  function textOf(el) {
    return (el && el.textContent || '').replace(/\s+/g, ' ').trim();
  }

  // 5-strategy label detection, reimplemented independently (conceptually
  // similar to filler_utils.js's getLabelForEl, but NOT imported/shared code
  // — see module docstring on why that matters here).
  function findLabel(el) {
    if (el.getAttribute('aria-label')) {
      return { text: el.getAttribute('aria-label').trim(), strategy: 'aria-label' };
    }
    if (el.id) {
      const explicit = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (explicit) return { text: textOf(explicit), strategy: 'label-for' };
    }
    const wrapping = el.closest('label');
    if (wrapping) return { text: textOf(wrapping), strategy: 'wrapping-label' };
    const labelledBy = el.getAttribute('aria-labelledby');
    if (labelledBy) {
      const parts = labelledBy.split(/\s+/)
        .map(id => document.getElementById(id))
        .filter(Boolean)
        .map(textOf);
      if (parts.length) return { text: parts.join(' ').trim(), strategy: 'aria-labelledby' };
    }
    // nearest preceding text node/sibling as a last-resort guess
    let sib = el.previousElementSibling;
    let hops = 0;
    while (sib && hops < 3) {
      const t = textOf(sib);
      if (t) return { text: t, strategy: 'preceding-text' };
      sib = sib.previousElementSibling;
      hops++;
    }
    return { text: '', strategy: null };
  }

  function ancestorClasses(el) {
    const chain = [];
    let node = el.parentElement;
    let hops = 0;
    while (node && hops < 8) {
      if (node.className && typeof node.className === 'string') {
        chain.push(node.className.trim());
      }
      node = node.parentElement;
      hops++;
    }
    return chain;
  }

  function nearestSection(el) {
    let node = el.parentElement;
    let hops = 0;
    while (node && hops < 10) {
      const heading = node.querySelector(':scope > h1, :scope > h2, :scope > h3, :scope > h4, :scope > legend');
      if (heading) return textOf(heading);
      node = node.parentElement;
      hops++;
    }
    return null;
  }

  function nearbyText(el) {
    const parent = el.parentElement;
    if (!parent) return '';
    return textOf(parent).slice(0, 500);
  }

  function sanitizedContainerHTML(el) {
    const container = el.closest('div,fieldset,section') || el.parentElement || el;
    const clone = container.cloneNode(true);
    clone.querySelectorAll('input,select,textarea').forEach(node => {
      node.removeAttribute('value');
      node.removeAttribute('checked');
      node.removeAttribute('selected');
    });
    return clone.outerHTML.slice(0, 4000);
  }

  function identityHash(tag, htmlType, name, id, autocomplete, role) {
    const raw = [tag, htmlType, name, id, autocomplete, role].join('|');
    // djb2 — stable, dependency-free, sufficient for dedup identity (not security).
    let hash = 5381;
    for (let i = 0; i < raw.length; i++) {
      hash = ((hash << 5) + hash + raw.charCodeAt(i)) >>> 0;
    }
    return hash.toString(16);
  }

  function baseAttrs(el) {
    const tag = el.tagName.toLowerCase();
    const htmlType = (el.getAttribute('type') || '').toLowerCase();
    const name = el.getAttribute('name') || '';
    const id = el.id || '';
    const autocomplete = el.getAttribute('autocomplete') || '';
    const role = el.getAttribute('role') || '';
    return { tag, htmlType, name, id, autocomplete, role };
  }

  function fieldRecord(el) {
    const { tag, htmlType, name, id, autocomplete, role } = baseAttrs(el);
    const label = findLabel(el);
    let inputType = tag;
    if (tag === 'input') inputType = htmlType || 'text';
    if (role === 'combobox') inputType = 'combobox';

    let options = null;
    if (tag === 'select') {
      options = Array.from(el.options).map(o => o.textContent.trim());
    }

    return {
      field_id_hash: identityHash(tag, htmlType, name, id, autocomplete, role),
      field_semantics: {
        label: label.text,
        label_found: !!label.text,
        label_strategy: label.strategy,
        section: nearestSection(el),
        ancestor_classes: ancestorClasses(el),
        nearby_text: nearbyText(el),
        options: options,
        description: '',
        placeholder: el.getAttribute('placeholder') || '',
        aria_label: el.getAttribute('aria-label') || '',
        aria_labelledby_text: '',
        input_mode: el.getAttribute('inputmode') || '',
        pattern: el.getAttribute('pattern') || '',
        max_length: el.getAttribute('maxlength') || null,
        container_html: sanitizedContainerHTML(el),
      },
      tag, html_type: htmlType, name, id, autocomplete, role,
      input_type: inputType,
      required: el.hasAttribute('required'),
      visible: isVisible(el),
      disabled: !!el.disabled,
      read_only: !!el.readOnly,
      hidden: isHidden(el),
    };
  }

  function groupRecord(groupName, els) {
    const first = els[0];
    const label = findLabel(first.closest('fieldset') || first.parentElement || first);
    return {
      field_id_hash: identityHash('group', groupName, els.map(e => e.value || '').join(','), '', '', els[0].getAttribute('role') || ''),
      field_semantics: {
        label: label.text,
        label_found: !!label.text,
        label_strategy: label.strategy,
        section: nearestSection(first),
        ancestor_classes: ancestorClasses(first),
        nearby_text: nearbyText(first),
      },
      input_type: groupName,
      options: els.map(el => ({
        value: el.value || '',
        text: findLabel(el).text || textOf(el.closest('label')) || '',
        visible: isVisible(el),
        disabled: !!el.disabled,
      })),
    };
  }

  const fields = [];
  const seen = new Set();

  // Exhaustive discovery — every input/select/textarea/role=combobox|radio|checkbox,
  // independent of whether a label exists (deliberate correction vs. label-first
  // discovery — see FORM_ENGINE_DESIGN.md §3.6a).
  const candidates = document.querySelectorAll(
    'input, select, textarea, [role="combobox"], [role="radio"], [role="checkbox"]'
  );

  const radioGroups = {};
  const checkboxSingles = [];

  candidates.forEach(el => {
    if (seen.has(el)) return;
    seen.add(el);

    const type = (el.getAttribute('type') || '').toLowerCase();
    const role = el.getAttribute('role') || '';

    if (type === 'radio' || role === 'radio') {
      const key = el.getAttribute('name') || el.getAttribute('data-group') || 'ungrouped';
      (radioGroups[key] = radioGroups[key] || []).push(el);
      return;
    }
    if (type === 'checkbox' || role === 'checkbox') {
      const key = el.getAttribute('name');
      if (key) {
        (radioGroups['checkbox:' + key] = radioGroups['checkbox:' + key] || []).push(el);
      } else {
        checkboxSingles.push(el);
      }
      return;
    }
    fields.push(fieldRecord(el));
  });

  Object.entries(radioGroups).forEach(([key, els]) => {
    fields.push(groupRecord(key.startsWith('checkbox:') ? 'checkbox_group' : 'radio_group', els));
  });
  checkboxSingles.forEach(el => fields.push(fieldRecord(el)));

  return { fields, total_candidates: candidates.length };
}
"""

_FIND_GREENHOUSE_IFRAME_JS = r"""
() => {
  const iframe = Array.from(document.querySelectorAll('iframe')).find(f => {
    try {
      const host = new URL(f.src, location.href).hostname;
      return host === 'job-boards.greenhouse.io' || host === 'boards.greenhouse.io';
    } catch (e) {
      return false;
    }
  });
  return iframe ? iframe.src : null;
}
"""

_APPLY_CLICK_JS = r"""
() => {
  const candidates = Array.from(document.querySelectorAll('button, a, [role="button"]'))
    .filter(el => {
      if (el.offsetParent === null) return false;
      const text = (el.textContent || '').trim();
      return /apply/i.test(text) && text.length < 40;
    });
  if (candidates.length === 0) return { clicked: false, ambiguous: false, candidateCount: 0 };
  // Prefer the largest/most prominent (by rendered area) if multiple.
  candidates.sort((a, b) => {
    const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
    return (rb.width * rb.height) - (ra.width * ra.height);
  });
  candidates[0].click();
  return { clicked: true, ambiguous: candidates.length > 1, candidateCount: candidates.length };
}
"""


# ---------------------------------------------------------------------------
# DOM stability wait — reimplemented independently, not imported from
# extension/filler_utils.js's waitForDomStability (same founding principle).
# ---------------------------------------------------------------------------

async def _wait_for_dom_stability(page: Page) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=_DOM_STABILITY_MAX_WAIT_MS)
    except Exception:
        pass
    await page.wait_for_timeout(_DOM_STABILITY_QUIET_MS)


def _looks_blocked(html: str, status: int | None) -> bool:
    if status is not None and status in (403, 429):
        return True
    return bool(_BLOCK_SIGNATURES.search(html[:5000]))


async def _crawl_one(browser, job: dict) -> tuple[dict, str, bytes]:
    """Returns (manifest_record, extraction_status, raw_html_bytes)."""
    job_id, ats, apply_url, company_name = job["job_id"], job["ats"], job["apply_url"], job["company_name"]
    crawl_started_at = datetime.now(timezone.utc).isoformat()

    apply_click_needed = False
    apply_click_ambiguous = False
    extraction_status = "error"
    error_detail = None
    fields: list[dict] = []
    html = ""
    crawled_url = apply_url
    page = None

    try:
        # Deliberately inside the try: under concurrency, a crashed/closed
        # browser process can make new_page() itself raise
        # (TargetClosedError). That must produce a per-job 'error' record,
        # not an unhandled exception that propagates through asyncio.gather
        # and kills every other in-flight worker (confirmed live 2026-07-26 —
        # took down a 19K-job run at ~2,855/19,412).
        #
        # wait_for is required here, not just goto's own timeout: on a
        # memory-starved machine (confirmed live 2026-07-26, ~245MB free),
        # new_page() itself can hang indefinitely waiting for the OS/browser
        # to allocate a new process — with no timeout of its own, a starved
        # worker just sits forever with no way to ever reach the except
        # block. Two of three workers did exactly this in the field.
        page = await asyncio.wait_for(browser.new_page(user_agent=_USER_AGENT), timeout=_GOTO_TIMEOUT_MS / 1000)
        response = await page.goto(apply_url, timeout=_GOTO_TIMEOUT_MS, wait_until="domcontentloaded")
        await _wait_for_dom_stability(page)

        # Some Greenhouse jobs are embedded via <iframe src="job-boards.greenhouse.io/embed/...">
        # on the company's own career site rather than served as a standalone
        # job-boards.greenhouse.io page. The top-level document in that case is
        # just site chrome (search bar, cookie consent) — the real form lives at
        # the iframe's src. Detect it and re-navigate there so extraction runs
        # against the actual form, not the embedding page.
        already_on_greenhouse_host = any(
            host in apply_url for host in ("job-boards.greenhouse.io", "boards.greenhouse.io")
        )
        iframe_src = None if already_on_greenhouse_host else await page.evaluate(_FIND_GREENHOUSE_IFRAME_JS)
        if iframe_src and iframe_src != apply_url:
            crawled_url = iframe_src
            response = await page.goto(iframe_src, timeout=_GOTO_TIMEOUT_MS, wait_until="domcontentloaded")
            await _wait_for_dom_stability(page)

        html = await page.content()
        status_code = response.status if response else None

        if _looks_blocked(html, status_code):
            extraction_status = "likely_blocked"
            error_detail = f"block signature or status={status_code} on initial load"
        else:
            result = await page.evaluate(_EXTRACTION_JS)
            if result["total_candidates"] == 0:
                click_result = await page.evaluate(_APPLY_CLICK_JS)
                if click_result["clicked"]:
                    apply_click_needed = True
                    apply_click_ambiguous = click_result["ambiguous"]
                    await _wait_for_dom_stability(page)
                    html = await page.content()
                    if _looks_blocked(html, None):
                        extraction_status = "likely_blocked"
                        error_detail = "block signature after apply-click"
                    else:
                        result = await page.evaluate(_EXTRACTION_JS)
                        fields = result["fields"]
                        extraction_status = "ok" if fields else "apply_button_clicked_no_form"
                else:
                    extraction_status = "no_form_found"
            else:
                fields = result["fields"]
                extraction_status = "ok" if fields else "no_form_found"
    except Exception as exc:
        error_detail = f"{type(exc).__name__}: {exc}"
        extraction_status = "error"
    finally:
        if page is not None:
            try:
                await page.close()
            except Exception:
                pass

    crawl_finished_at = datetime.now(timezone.utc).isoformat()
    page_html_path = f"pages/{job_id}.html.gz"

    record = {
        "job_id": job_id,
        "ats": ats,
        "company_name": company_name,
        "url": apply_url,
        "crawled_url": crawled_url,
        "crawl_started_at": crawl_started_at,
        "crawl_finished_at": crawl_finished_at,
        "apply_click_needed": apply_click_needed,
        "apply_click_ambiguous": apply_click_ambiguous,
        "extraction_status": extraction_status,
        "error_detail": error_detail,
        "page_html_path": page_html_path if html else None,
        "harvester_version": HARVESTER_VERSION,
        "fields": fields,
    }
    return record, extraction_status, html.encode("utf-8") if html else b""


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _fetch_target_jobs(limit: int | None, retry_errors: bool) -> list[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        if retry_errors:
            rows = await conn.fetch(
                """
                SELECT j.job_id, j.ats, j.apply_url, j.company_name
                FROM jobs j
                JOIN corpus_crawl_state s ON s.job_id = j.job_id AND s.ats = j.ats
                WHERE j.ats = 'greenhouse' AND j.apply_url <> '' AND s.extraction_status = 'error'
                ORDER BY j.job_id
                """
            )
        else:
            rows = await conn.fetch(
                """
                SELECT j.job_id, j.ats, j.apply_url, j.company_name
                FROM jobs j
                LEFT JOIN corpus_crawl_state s ON s.job_id = j.job_id AND s.ats = j.ats
                WHERE j.ats = 'greenhouse' AND j.apply_url <> '' AND s.job_id IS NULL
                ORDER BY j.job_id
                """
            )
    jobs = [dict(r) for r in rows]
    if limit is not None:
        jobs = jobs[:limit]
    return jobs


async def _upsert_crawl_state(job_id: str, ats: str, extraction_status: str, error_detail: str | None) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO corpus_crawl_state
                (job_id, ats, extraction_status, page_html_path, harvester_version, error_detail)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (job_id, ats) DO UPDATE
                SET extraction_status = EXCLUDED.extraction_status,
                    page_html_path = EXCLUDED.page_html_path,
                    crawled_at = NOW(),
                    harvester_version = EXCLUDED.harvester_version,
                    error_detail = EXCLUDED.error_detail
            """,
            job_id, ats, extraction_status, f"pages/{job_id}.html.gz", HARVESTER_VERSION, error_detail,
        )


# ---------------------------------------------------------------------------
# Main crawl loop
# ---------------------------------------------------------------------------

class _SharedState:
    """Coordination across concurrent workers — one instance per run.

    block_streak is a global smoke alarm (not per-tenant): with N workers
    interleaving results from many different tenants, a real streak of
    organic failures is unremarkable up to _BLOCK_STREAK_THRESHOLD, so this
    stays a simple shared counter rather than per-host tracking.
    """

    def __init__(self, total: int) -> None:
        self.total = total
        self.completed = 0
        self.block_streak = 0
        self.totals: dict[str, int] = {}
        self.stop_requested = False
        self.write_lock = asyncio.Lock()
        self.browser = None
        self.browser_lock = asyncio.Lock()
        self.jobs_since_launch = 0


# Proactively recycle the shared browser process every N jobs, not just on
# outright death. Pages are closed after every job (_crawl_one's finally
# block) so steady-state memory *should* stay flat, but Chromium/Playwright
# are known to creep in real-world long-running sessions even with clean
# page lifecycles (renderer/cache state not always fully reclaimed) — a real
# risk flagged 2026-07-26 on this machine's already-tight RAM headroom
# (~245MB free at the last crash) rather than something ruled out by reading
# this code alone. Recycling bounds any such creep to a small window instead
# of letting it accumulate across a ~16K-job run.
_BROWSER_RECYCLE_EVERY = 300


async def _get_or_relaunch_browser(p, state: "_SharedState"):
    """Returns the shared browser, relaunching it if dead OR due for recycle.

    Dead-browser case confirmed live 2026-07-26: one Browser.new_page()
    TargetClosedError propagated through asyncio.gather and killed an entire
    19K-job run at ~2,855/19,412, losing 6 other workers' in-flight progress.
    Every subsequent new_page() call on a dead browser fails identically, so
    relaunching here caps the cost at one job, not the rest of the queue.
    """
    async with state.browser_lock:
        due_for_recycle = state.jobs_since_launch >= _BROWSER_RECYCLE_EVERY
        if state.browser is None or not state.browser.is_connected() or due_for_recycle:
            if state.browser is not None:
                reason = "scheduled recycle" if due_for_recycle else "connection lost"
                logger.warning("Relaunching browser (%s, %d jobs since last launch).", reason, state.jobs_since_launch)
                try:
                    await state.browser.close()
                except Exception:
                    pass
            state.browser = await p.chromium.launch(headless=True)
            state.jobs_since_launch = 0
        return state.browser


async def _worker(
    worker_id: int,
    p,
    job_queue: "asyncio.Queue[dict]",
    state: _SharedState,
    manifest_f,
) -> None:
    while True:
        try:
            job = job_queue.get_nowait()
        except asyncio.QueueEmpty:
            return

        if state.stop_requested:
            job_queue.task_done()
            continue

        # The entire per-job body is defensive: nothing here may propagate
        # out of this loop iteration. asyncio.gather cancels every sibling
        # worker the instant ANY one of them raises — confirmed live
        # 2026-07-26 (a single Browser.new_page() TargetClosedError took
        # down a 19K-job run at ~2,855/19,412, discarding the other 6
        # workers' in-flight jobs). A malformed job record, a DB hiccup, or
        # any other surprise here must degrade to one 'error' row, never a
        # run-ending exception.
        try:
            browser = await _get_or_relaunch_browser(p, state)
            async with state.browser_lock:
                state.jobs_since_launch += 1
            record, status, html_bytes = await _crawl_one(browser, job)

            if html_bytes:
                gz_path = PAGES_DIR / f"{job['job_id']}.html.gz"
                with gzip.open(gz_path, "wb") as f:
                    f.write(html_bytes)

            async with state.write_lock:
                manifest_f.write(json.dumps(record) + "\n")
                manifest_f.flush()

                await _upsert_crawl_state(job["job_id"], job["ats"], status, record["error_detail"])

                state.completed += 1
                state.totals[status] = state.totals.get(status, 0) + 1
                logger.info(
                    "[w%d %d/%d] %s (%s) -> %s%s",
                    worker_id, state.completed, state.total,
                    job["company_name"] or job["job_id"], job["job_id"],
                    status,
                    f" ({len(record['fields'])} fields)" if status == "ok" else "",
                )

                if status in _FAILURE_STATUSES:
                    state.block_streak += 1
                else:
                    state.block_streak = 0

                if state.block_streak >= _BLOCK_STREAK_THRESHOLD and not state.stop_requested:
                    state.stop_requested = True
                    logger.warning(
                        "Stopping early: %d consecutive failures/likely-blocked results across "
                        "workers — this looks like a block, not organic bad-form noise. "
                        "%d of %d jobs left un-attempted (safe to resume later).",
                        state.block_streak, state.total - state.completed, state.total,
                    )
        except Exception as exc:
            logger.error("[w%d] unhandled exception on job %s: %s: %s", worker_id, job.get("job_id"), type(exc).__name__, exc)
        finally:
            job_queue.task_done()

        await asyncio.sleep(random.uniform(_JITTER_MIN_S, _JITTER_MAX_S))


async def run_harvest(limit: int | None, retry_errors: bool, concurrency: int) -> None:
    await init_db()
    try:
        jobs = await _fetch_target_jobs(limit, retry_errors)
        if not jobs:
            logger.info("Nothing to crawl — all targeted jobs already have crawl_state rows.")
            return

        logger.info(
            "Crawling %d Greenhouse job(s) (retry_errors=%s, concurrency=%d)",
            len(jobs), retry_errors, concurrency,
        )

        PAGES_DIR.mkdir(parents=True, exist_ok=True)
        CORPUS_DIR.mkdir(parents=True, exist_ok=True)

        state = _SharedState(total=len(jobs))
        start_time = time.monotonic()

        job_queue: "asyncio.Queue[dict]" = asyncio.Queue()
        for job in jobs:
            job_queue.put_nowait(job)

        async with async_playwright() as p:
            state.browser = await p.chromium.launch(headless=True)
            try:
                with MANIFEST_PATH.open("a", encoding="utf-8") as manifest_f:
                    workers = [
                        asyncio.create_task(_worker(w, p, job_queue, state, manifest_f))
                        for w in range(1, concurrency + 1)
                    ]
                    # Workers are now individually exception-safe (see _worker's
                    # inner try/except), so gather cannot be short-circuited by
                    # one worker's failure — but return_exceptions=True stays as
                    # defense in depth in case a future change reintroduces a
                    # gap, so one bug can't silently cancel the other workers.
                    await asyncio.gather(*workers, return_exceptions=True)
            finally:
                if state.browser is not None:
                    try:
                        await state.browser.close()
                    except Exception:
                        pass

        elapsed = time.monotonic() - start_time
        _hr = "─" * 62
        print(_hr)
        print("  CORPUS HARVEST COMPLETE")
        for status, count in sorted(state.totals.items(), key=lambda kv: -kv[1]):
            print(f"  {status:32s} {count:4d}")
        print(f"  elapsed: {elapsed / 60:.1f} min")
        print(_hr, flush=True)
    finally:
        await close_db()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Cap number of jobs crawled (smoke testing)")
    parser.add_argument("--retry-errors", action="store_true", help="Only re-attempt jobs with extraction_status='error'")
    parser.add_argument(
        "--concurrency", type=int, default=_DEFAULT_CONCURRENCY,
        help=f"Number of concurrent browser pages (default {_DEFAULT_CONCURRENCY}, matches original sequential behavior)",
    )
    args = parser.parse_args()

    asyncio.run(run_harvest(limit=args.limit, retry_errors=args.retry_errors, concurrency=args.concurrency))


if __name__ == "__main__":
    main()
