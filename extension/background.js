// Service worker — fully stateless in memory. All state lives in chrome.storage.local.
// Every handler reads fresh, mutates, writes back. Flow is event-driven via chrome.alarms.

importScripts('api.js');

const DEBUG_MODE = true; // set false before shipping

const DEFAULT_STATE = {
  phase: 'idle',           // idle | fetching | tab_open | filling | awaiting_review | post_submit_wait
  current_job: null,       // { job_id, job_ats, apply_url, company_name, title } | null
  current_tab_id: null,
  phase_started_at: null,
  paused: false,
  paused_at: null,
  auto_submit: false,
  needs_sponsorship: false,
  pending_review: null,    // { job_id, job_ats, apply_url, company_name, title, reason } | null
  pending_submission: null, // { tab_id, job_id, job_ats, url_at_submit, started_at } | null
};

// awaiting_review is not lease-tracked server-side (the human decides when to
// submit), but an abandoned tab shouldn't hold a phantom claim forever.
const REVIEW_TIMEOUT_MS = 30 * 60 * 1000;

// A content script's JS context (including any in-page success poll) is
// destroyed the instant the tab navigates — confirmed by live testing
// against Greenhouse: a real submit click navigated to the confirmation
// page, but the in-page poll never got another tick to observe it, so
// 'success' was never sent. tabs.onUpdated lives in the service worker,
// which survives that navigation, so it's the only reliable place to catch
// a submission that results in a full page navigation (as opposed to an
// SPA-style same-page "thank you" render, which the content script's own
// detection already handles fine).
const SUBMISSION_VERIFY_TIMEOUT_MS = 30 * 1000;

async function getState() {
  const stored = await chrome.storage.local.get(Object.keys(DEFAULT_STATE));
  return { ...DEFAULT_STATE, ...stored };
}

async function resetToIdle(extra = {}) {
  await chrome.storage.local.set({
    phase: 'idle',
    current_job: null,
    current_tab_id: null,
    phase_started_at: null,
    ...extra,
  });
}

async function closeTab(tabId) {
  if (!tabId) return;
  try { await chrome.tabs.remove(tabId); } catch { /* already closed */ }
}

// Two independent paths can report a submission (the content script's own
// in-page detection, and the background's post-navigation verifier below) —
// idempotent so it doesn't matter which one wins or if both fire.
async function completeSubmission(job, snapshots) {
  const state = await getState();
  if (state.phase === 'post_submit_wait') return; // already handled

  if (job) {
    await markSubmitted(job.job_id, job.job_ats, snapshots);
  }
  await chrome.storage.local.set({
    phase: 'post_submit_wait',
    pending_review: null,
    pending_submission: null,
  });
  const delayMin = 0.5 + Math.random() * 1;
  await chrome.alarms.create('next_job_alarm', { delayInMinutes: delayMin });
  // DEBUG: tab left open
  // await closeTab(job's tab id);
}

// Runs inside the freshly-navigated page (injected, not a content script) to
// check whether it looks like a submission confirmation. Kept deliberately
// generic (not ATS-specific) — scoped to the one bug this fixes: Greenhouse
// navigating to a static "thank you" page that the original content script
// could never observe because its JS context died with the old page.
function verifySubmissionPage() {
  const text = document.body ? document.body.innerText : '';
  return /thank you|application received|successfully submitted/i.test(text);
}

// Stale detection — called on every alarm before anything else.
// Returns true if stale was detected and local state was reset.
//
// The client NO LONGER declares the job failed/abandoned here. Client-span
// deaths are reaped SERVER-side by the lease-expiry sweep (a submitting row
// whose lease is >10 min stale -> abandoned). We only reset our own in-memory
// state so we can pick up the next job; the server owns the row's fate.
async function checkStale(state) {
  if (state.phase === 'idle' || state.phase === 'post_submit_wait') return false;

  if (state.phase === 'awaiting_review') {
    if (state.phase_started_at && Date.now() - state.phase_started_at > REVIEW_TIMEOUT_MS) {
      if (state.current_job) {
        await markReleased(state.current_job.job_id, state.current_job.job_ats, 'review_timeout');
      }
      await closeTab(state.current_tab_id);
      await resetToIdle({ pending_review: null });
      return true;
    }
    return false;
  }

  const TEN_MIN = 10 * 60 * 1000;
  if (state.phase_started_at && Date.now() - state.phase_started_at > TEN_MIN) {
    // await closeTab(state.current_tab_id);
    await resetToIdle();
    return true;
  }
  return false;
}

async function runPollCycle() {
  const state = await getState();
  if (await checkStale(state)) return;

  const fresh = await getState();
  if (fresh.paused || fresh.phase !== 'idle') return;

  await chrome.storage.local.set({ phase: 'fetching' });

  const job = await claimNextJob();
  if (!job) {
    await chrome.storage.local.set({ phase: 'idle' });
    return;
  }

  await chrome.storage.local.set({
    phase: 'tab_open',
    current_job: job,
    phase_started_at: Date.now(),
  });

  const tab = await chrome.tabs.create({ url: job.apply_url, active: false });
  await chrome.storage.local.set({ current_tab_id: tab.id });
}

// Initialize defaults on install and startup
async function initDefaults() {
  const stored = await chrome.storage.local.get(Object.keys(DEFAULT_STATE));
  const toSet = {};
  for (const [key, val] of Object.entries(DEFAULT_STATE)) {
    if (!(key in stored)) toSet[key] = val;
  }
  if (Object.keys(toSet).length > 0) {
    await chrome.storage.local.set(toSet);
  }
}

chrome.runtime.onInstalled.addListener(async () => {
  await initDefaults();
  await chrome.alarms.create('poll_alarm', { periodInMinutes: 5 });
});

chrome.runtime.onStartup.addListener(async () => {
  await initDefaults();
  const existing = await chrome.alarms.get('poll_alarm');
  if (!existing) {
    await chrome.alarms.create('poll_alarm', { periodInMinutes: 5 });
  }
});

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === 'poll_alarm' || alarm.name === 'next_job_alarm') {
    if (alarm.name === 'next_job_alarm') {
      // next_job_alarm fires after successful apply; reset phase then trigger poll
      await chrome.storage.local.set({ phase: 'idle' });
    }
    await runPollCycle();
  }
});

// Tab updated: when our tab finishes loading during tab_open, advance phase to filling.
// Content script initiates the handshake — we don't message it here.
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status !== 'complete') return;

  const state = await getState();

  if (tabId === state.current_tab_id && state.phase === 'tab_open') {
    await chrome.storage.local.set({ phase: 'filling' });
  }

  // Post-submit-click navigation check (see pending_submission comment above
  // DEFAULT_STATE). Only fires if a click was tracked for this exact tab and
  // the page actually changed — a same-page DOM update (SPA confirmation)
  // won't trigger onUpdated at all, which is fine: the content script's own
  // MutationObserver/poll already covers that case.
  const pending = state.pending_submission;
  if (!pending || pending.tab_id !== tabId) return;

  if (Date.now() - pending.started_at > SUBMISSION_VERIFY_TIMEOUT_MS) {
    await chrome.storage.local.set({ pending_submission: null });
    return;
  }
  if (!tab.url || tab.url === pending.url_at_submit) return; // didn't actually navigate

  try {
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId },
      func: verifySubmissionPage,
    });
    if (result) {
      await completeSubmission({ job_id: pending.job_id, job_ats: pending.job_ats });
    }
  } catch (err) {
    // Page may be a chrome:// URL, cross-origin restricted, or the tab
    // closed mid-check — nothing to do, the timeout above cleans this up.
    console.log('Persift: submission verifier injection failed —', err && err.message);
  }
});

// Tab removed: if user closes the active tab mid-fill, mark failed and reset.
chrome.tabs.onRemoved.addListener(async (tabId) => {
  const state = await getState();
  if (tabId !== state.current_tab_id) return;

  if (state.phase === 'awaiting_review') {
    if (state.current_job) {
      await markReleased(state.current_job.job_id, state.current_job.job_ats, 'tab_closed_by_user');
    }
    await resetToIdle({ pending_review: null });
    return;
  }

  if (state.phase !== 'filling' && state.phase !== 'tab_open') return;
  // if (state.current_job) {
  //   await markReleased(state.current_job.job_id, state.current_job.job_ats, 'tab_closed_by_user');
  // }
  // await resetToIdle();
});

// Message listener — content script and popup communicate here.
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  handleMessage(message, sender, sendResponse);
  return true; // keep sendResponse alive for async reply
});

// Messages that report on a specific in-flight job (as opposed to popup
// actions, which have no sender.tab at all). A stale tab left alive past its
// job's lifetime (given up on, released, replaced by a new claim) must not
// be able to act on whatever job background.js currently thinks is current —
// found by Fable's audit as a sharper version of the 'ready' cross-job bug
// fixed earlier tonight: content scripts now stay alive up to 30 min
// (awaiting_review), so an old tab surviving past its job's end is the
// normal case, not a rare race.
const TAB_SCOPED_MESSAGES = new Set(['success', 'failed', 'needs_review', 'heartbeat', 'submit_clicked']);

async function handleMessage(message, sender, sendResponse) {
  const state = await getState();

  if (TAB_SCOPED_MESSAGES.has(message.type) &&
      (!sender.tab || sender.tab.id !== state.current_tab_id)) {
    // A genuine 'success' from a stale tab (job was given up on / reassigned,
    // but the user submitted the old tab anyway) would otherwise vanish with
    // no record anywhere. message.job_id/job_ats travel with every message
    // (see greenhouse.js/ashby.js send()) specifically so we can still
    // identify and log which job this was about, for manual reconciliation,
    // instead of silently dropping a real submission on the floor.
    if (message.type === 'success' && message.job_id) {
      console.warn(
        'Persift: stale-tab success ignored — job may need manual reconciliation:',
        { job_id: message.job_id, job_ats: message.job_ats, current_job: state.current_job }
      );
    }
    sendResponse({ ok: false, error: 'stale_tab' });
    return;
  }

  switch (message.type) {
    case 'debug_log': {
      // Content-script console output dies with the tab on navigation (e.g.
      // Greenhouse's post-submit redirect) before it can be read. Relay into
      // the service worker's console (survives tab navigation/closure) and
      // into storage so it can be dumped after the fact via
      // chrome.storage.local.get('debug_log', console.log).
      console.log('[content]', message.text);
      const { debug_log = [] } = await chrome.storage.local.get('debug_log');
      debug_log.push({ t: Date.now(), text: message.text });
      await chrome.storage.local.set({ debug_log: debug_log.slice(-200) });
      sendResponse({ ok: true });
      break;
    }

    case 'ready': {
      // Only the tab we actually opened for current_job gets fed job data.
      // Content scripts auto-inject into ANY matching Greenhouse/Ashby URL
      // (manifest match patterns aren't scoped to queued jobs), so a tab the
      // user opened manually — or a leftover tab from a prior job — must not
      // be handed whatever job happens to be in memory (e.g. one parked in
      // awaiting_review, which now legitimately keeps current_job set).
      if (!sender.tab || sender.tab.id !== state.current_tab_id) {
        sendResponse({ job: null });
        break;
      }
      await chrome.storage.local.set({ phase: 'filling' });
      const userId = await getUserId();
      const profile = userId ? await getProfile(userId) : null;
      sendResponse({
        job: state.current_job,
        auto_submit: state.auto_submit,
        needs_sponsorship: state.needs_sponsorship,
        user_id: userId,
        ...(profile || {}),
      });
      break;
    }

    case 'submit_clicked': {
      // Content script's own detectSuccess() poll only catches SPA-style
      // same-page confirmations. If the click causes a full navigation, that
      // poll's JS context dies with the page before it can observe the
      // result — so we also track the click here, where tabs.onUpdated can
      // catch the navigation regardless of what happens to the content
      // script that started it.
      if (!sender.tab) { sendResponse({ ok: false }); break; }
      await chrome.storage.local.set({
        pending_submission: {
          tab_id: sender.tab.id,
          job_id: message.job_id,
          job_ats: message.job_ats,
          url_at_submit: message.url_at_submit,
          started_at: Date.now(),
        },
      });
      sendResponse({ ok: true });
      break;
    }

    case 'success': {
      await completeSubmission(state.current_job, message.snapshots);
      sendResponse({ ok: true });
      break;
    }

    case 'failed': {
      // Clean in-client failure = release the claim; server decides retry vs
      // terminal by count. Client never writes 'abandoned' itself.
      if (state.current_job) {
        await markReleased(state.current_job.job_id, state.current_job.job_ats, message.reason);
      }
      // DEBUG: tab left open
      // await closeTab(state.current_tab_id);
      await resetToIdle();
      sendResponse({ ok: true });
      break;
    }

    case 'heartbeat': {
      // Bump local freshness AND renew the server-side lease so cleanup won't
      // reap an actively-filling job.
      await chrome.storage.local.set({ phase_started_at: Date.now() });
      if (state.current_job) {
        await sendHeartbeat(state.current_job.job_id, state.current_job.job_ats);
      }
      sendResponse({ ok: true });
      break;
    }

    case 'fetch_resume': {
      const blob = await getResumePdf(message.job_id, message.job_ats);
      if (!blob) { sendResponse({ ok: false }); break; }
      const buffer = await blob.arrayBuffer();
      const bytes = new Uint8Array(buffer);
      let binary = '';
      for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
      sendResponse({ ok: true, data: btoa(binary) });
      break;
    }

    case 'fetch_document': {
      const userId = await getUserId();
      if (!userId) { sendResponse({ ok: false }); break; }
      const blob = await getDocument(userId, message.doc_type);
      if (!blob) { sendResponse({ ok: false }); break; }
      const buffer = await blob.arrayBuffer();
      const bytes = new Uint8Array(buffer);
      let binary = '';
      for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
      sendResponse({ ok: true, data: btoa(binary) });
      break;
    }

    case 'needs_review': {
      if (state.current_job) {
        await markAwaitingReview(state.current_job.job_id, state.current_job.job_ats, message.reason || 'awaiting_user_submit');
      }
      // Unlike other review reasons, 'awaiting_user_submit' means the form IS
      // filled and the content script is staying alive on the page to detect
      // the human's own Submit click. Keep current_job so that eventual
      // 'success' message (or the popup's manual-confirm fallback) can still
      // resolve markSubmitted. Other reasons (no form found, unsupported
      // layout) have nothing left to detect, but we keep current_job here too
      // so the popup's fallback ('I submitted it' / 'Give up') still works
      // uniformly for any pending_review.
      await chrome.storage.local.set({
        phase: 'awaiting_review',
        phase_started_at: Date.now(),
        pending_review: state.current_job
          ? { ...state.current_job, reason: message.reason }
          : null,
      });
      sendResponse({ ok: true });
      break;
    }

    // Popup actions
    case 'pause': {
      await chrome.storage.local.set({ paused: true, paused_at: Date.now() });
      sendResponse({ ok: true });
      break;
    }
    case 'resume': {
      await chrome.storage.local.set({ paused: false, paused_at: null });
      sendResponse({ ok: true });
      break;
    }
    case 'skip': {
      // User skips the current job = release the claim. Server: skip once ->
      // ready (re-served next poll); skip twice -> abandoned (terminal). Count
      // does the work, not the client.
      if (state.current_job) {
        await markReleased(state.current_job.job_id, state.current_job.job_ats, 'user_skipped');
      }
      await closeTab(state.current_tab_id);
      await resetToIdle();
      sendResponse({ ok: true });
      break;
    }
    // Fallback for when the review tab/content-script is gone (discarded,
    // closed, reloaded) so the live-detection path in the content script
    // can't fire 'success' itself. User self-attests they submitted on the
    // real page. No snapshots (that requires DOM access we no longer have).
    case 'manual_submit_confirm': {
      if (state.pending_review) {
        await markSubmitted(state.pending_review.job_id, state.pending_review.job_ats);
      }
      await closeTab(state.current_tab_id);
      await resetToIdle({ pending_review: null });
      sendResponse({ ok: true });
      break;
    }

    // User gives up on a parked review job without submitting it.
    case 'clear_review': {
      if (state.pending_review) {
        await markReleased(state.pending_review.job_id, state.pending_review.job_ats, 'user_gave_up_review');
      }
      await closeTab(state.current_tab_id);
      await resetToIdle({ pending_review: null });
      sendResponse({ ok: true });
      break;
    }

    default:
      sendResponse({ ok: false, error: 'unknown_message_type' });
  }
}
