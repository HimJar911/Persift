// Shared API module — injected into content scripts and imported by background.js
// via importScripts('api.js'). All functions are globals; no ES module syntax.

const BASE_URL = 'http://localhost:8000';

async function getUserId() {
  const { user_id } = await chrome.storage.local.get('user_id');
  return user_id || null;
}

// Atomically claim the next 'ready' application (server moves ready -> submitting
// and stamps a lease). Replaces the old GET /jobs/queue. Returns the job or null.
async function claimNextJob() {
  const user_id = await getUserId();
  if (!user_id) return null;
  try {
    const resp = await fetch(`${BASE_URL}/jobs/claim`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id }),
    });
    if (!resp.ok) return null;
    const data = await resp.json();
    return data.job || null;
  } catch { return null; }
}

// Confirm a submitted application. Fat endpoint: pass snapshots ({filled, submitted})
// only when review was on (auto-submit off) so the server records field corrections.
//
// Retries a few times on failure: a silent drop here (server never learns the
// job was submitted) leads to the row being reaped as abandoned and retried,
// i.e. a real duplicate application. The server-side endpoint is idempotent
// against a retry landing after a first call that actually succeeded, so it's
// safe to retry blindly. Only returns false once every attempt is exhausted —
// callers must treat that as "not confirmed," not as "failed cleanly."
const MARK_SUBMITTED_RETRY_DELAYS_MS = [1000, 3000, 6000];

async function markSubmitted(jobId, jobAts, snapshots) {
  const user_id = await getUserId();
  if (!user_id) return false;

  const body = { user_id, job_ats: jobAts };
  if (snapshots && snapshots.filled && snapshots.submitted) {
    body.snapshot_filled = snapshots.filled;
    body.snapshot_submitted = snapshots.submitted;
  }

  for (let attempt = 0; ; attempt++) {
    try {
      const resp = await fetch(`${BASE_URL}/jobs/${encodeURIComponent(jobId)}/submitted`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (resp.ok) return true;
    } catch { /* network error — fall through to retry/backoff below */ }

    if (attempt >= MARK_SUBMITTED_RETRY_DELAYS_MS.length) return false;
    await new Promise((r) => setTimeout(r, MARK_SUBMITTED_RETRY_DELAYS_MS[attempt]));
  }
}

// Fill done, auto-submit off: park for the user to review & submit.
async function markAwaitingReview(jobId, jobAts, reason) {
  const user_id = await getUserId();
  if (!user_id) return false;
  try {
    const resp = await fetch(`${BASE_URL}/jobs/${encodeURIComponent(jobId)}/awaiting_review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id, job_ats: jobAts, reason }),
    });
    return resp.ok;
  } catch { return false; }
}

// Client voluntarily gives up a claim it can't finish (skip / clean in-client
// failure). Server decides retry (-> ready) vs terminal (-> abandoned) by count.
// Replaces the old markFailed. The client NEVER declares a job abandoned itself;
// stale/dead claims are reaped server-side by the lease sweep.
async function markReleased(jobId, jobAts, reason) {
  const user_id = await getUserId();
  if (!user_id) return false;
  try {
    const resp = await fetch(`${BASE_URL}/jobs/${encodeURIComponent(jobId)}/released`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id, job_ats: jobAts, reason }),
    });
    return resp.ok;
  } catch { return false; }
}

// Renew the lease on the currently-claimed (submitting) job.
async function sendHeartbeat(jobId, jobAts) {
  const user_id = await getUserId();
  if (!user_id) return false;
  try {
    const resp = await fetch(`${BASE_URL}/jobs/${encodeURIComponent(jobId)}/heartbeat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id, job_ats: jobAts }),
    });
    return resp.ok;
  } catch { return false; }
}

async function getDocument(userId, docType) {
  try {
    const resp = await fetch(
      `${BASE_URL}/users/${encodeURIComponent(userId)}/documents/${encodeURIComponent(docType)}`
    );
    if (!resp.ok) return null;
    return await resp.blob();
  } catch { return null; }
}

async function getResumePdf(jobId, jobAts) {
  const user_id = await getUserId();
  if (!user_id) return null;
  try {
    const resp = await fetch(
      `${BASE_URL}/jobs/${encodeURIComponent(jobId)}/resume` +
      `?job_ats=${encodeURIComponent(jobAts)}&user_id=${encodeURIComponent(user_id)}`
    );
    if (!resp.ok) return null;
    return await resp.blob();
  } catch { return null; }
}

async function getProfile(userId) {
  try {
    const resp = await fetch(`${BASE_URL}/users/${encodeURIComponent(userId)}`);
    if (!resp.ok) return null;
    return await resp.json();
  } catch { return null; }
}

async function getQueueCount() {
  const user_id = await getUserId();
  if (!user_id) return null;
  try {
    const resp = await fetch(`${BASE_URL}/jobs/queue/count?user_id=${encodeURIComponent(user_id)}`);
    if (!resp.ok) return null;
    const data = await resp.json();
    return typeof data.count === 'number' ? data.count : null;
  } catch { return null; }
}
