// Service worker — fully stateless in memory. All state lives in chrome.storage.local.
// Every handler reads fresh, mutates, writes back. Flow is event-driven via chrome.alarms.

importScripts('api.js');

const DEFAULT_STATE = {
  phase: 'idle',           // idle | fetching | tab_open | filling | post_submit_wait
  current_job: null,       // { job_id, job_ats, apply_url, company_name, title } | null
  current_tab_id: null,
  phase_started_at: null,
  paused: false,
  paused_at: null,
  auto_submit: false,
  needs_sponsorship: false,
  pending_review: null,    // { job_id, job_ats, apply_url, company_name, title, reason } | null
};

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

// Stale detection — called on every alarm before anything else.
// Returns true if stale was detected and state was reset.
async function checkStale(state) {
  if (state.phase === 'idle' || state.phase === 'post_submit_wait') return false;
  const TEN_MIN = 10 * 60 * 1000;
  if (state.phase_started_at && Date.now() - state.phase_started_at > TEN_MIN) {
    if (state.current_job) {
      await markFailed(state.current_job.job_id, state.current_job.job_ats, 'stale_timeout');
    }
    await closeTab(state.current_tab_id);
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

  const job = await fetchNextJob();
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
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo) => {
  if (changeInfo.status !== 'complete') return;
  const state = await getState();
  if (tabId !== state.current_tab_id || state.phase !== 'tab_open') return;
  await chrome.storage.local.set({ phase: 'filling' });
});

// Tab removed: if user closes the active tab mid-fill, mark failed and reset.
chrome.tabs.onRemoved.addListener(async (tabId) => {
  const state = await getState();
  if (tabId !== state.current_tab_id) return;
  if (state.phase !== 'filling' && state.phase !== 'tab_open') return;
  if (state.current_job) {
    await markFailed(state.current_job.job_id, state.current_job.job_ats, 'tab_closed_by_user');
  }
  await resetToIdle();
});

// Message listener — content script and popup communicate here.
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  handleMessage(message, sendResponse);
  return true; // keep sendResponse alive for async reply
});

async function handleMessage(message, sendResponse) {
  const state = await getState();

  switch (message.type) {
    case 'ready': {
      await chrome.storage.local.set({ phase: 'filling' });
      const userId = await getUserId();
      sendResponse({
        job: state.current_job,
        auto_submit: state.auto_submit,
        needs_sponsorship: state.needs_sponsorship,
        user_id: userId,
      });
      break;
    }

    case 'success': {
      if (state.current_job) {
        await markApplied(state.current_job.job_id, state.current_job.job_ats);
      }
      await chrome.storage.local.set({ phase: 'post_submit_wait' });
      const delayMin = 0.5 + Math.random() * 1;
      await chrome.alarms.create('next_job_alarm', { delayInMinutes: delayMin });
      await closeTab(state.current_tab_id);
      sendResponse({ ok: true });
      break;
    }

    case 'failed': {
      if (state.current_job) {
        await markFailed(state.current_job.job_id, state.current_job.job_ats, message.reason);
      }
      await closeTab(state.current_tab_id);
      await resetToIdle();
      sendResponse({ ok: true });
      break;
    }

    case 'heartbeat': {
      await chrome.storage.local.set({ phase_started_at: Date.now() });
      sendResponse({ ok: true });
      break;
    }

    case 'needs_review': {
      if (state.current_job) {
        await markFailed(state.current_job.job_id, state.current_job.job_ats, 'skipped_complex');
      }
      await closeTab(state.current_tab_id);
      await resetToIdle({
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
      // Stop and skip current job
      if (state.current_job) {
        await markFailed(state.current_job.job_id, state.current_job.job_ats, 'user_skipped');
      }
      await closeTab(state.current_tab_id);
      await resetToIdle();
      sendResponse({ ok: true });
      break;
    }
    case 'clear_review': {
      await chrome.storage.local.set({ pending_review: null });
      sendResponse({ ok: true });
      break;
    }

    default:
      sendResponse({ ok: false, error: 'unknown_message_type' });
  }
}
