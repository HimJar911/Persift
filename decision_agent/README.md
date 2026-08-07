# decision_agent/ — laptop-side persistent decision agent

Runs on the user's Windows laptop, NOT on the VM. Holds one persistent
Claude Code session per ATS (via the `claude` CLI, subscription-billed —
not a metered API key) and makes checkpoint-halt decisions that
`orchestrate.py` on the VM can't auto-apply on its own (any
`NeedsHumanDecision`, or a `ProposedFix` that failed its gate/guardrail).

## Why this exists (see STATE.md / memory for full history)

`orchestrate.py`'s checkpoint loop, when it can't cleanly auto-apply every
proposed fix, sets `halted_for_review=True` and stops the run. The original
plan required a human to read the checkpoint report and manually decide.
This package automates that decision loop for unattended overnight runs,
while keeping the same hard ceiling `propose_fix.py` already has: it can
NEVER directly write to `category_mapping.py`, `taxonomy_v1.py`, the
cluster/corpus JSON files, or `extension/consent_policy.js` — only
propose/draft additions to those, logged for human review, never silently
applied. Every decision is either a real git commit (narrow fixes,
already gated) or a clearly-flagged proposal (new-category calls) — full
audit trail via git log + the checkpoint reports, nothing silently applied
outside what's visible there.

**Why local instead of Managed Agents (Anthropic's hosted agent API):**
Managed Agents bills per-token through the Claude API, a separate metered
surface from a Claude subscription. Running this as a `claude` CLI
subprocess authenticates via the same subscription login already active
on this machine (`claude auth` / Claude Code login) — decisions ride the
subscription instead of API spend. This was an explicit, deliberate
tradeoff: the alternative (Managed Agents, VM-hosted, zero laptop
dependency) was rejected specifically for cost, accepting in exchange that
the laptop must stay on and reachable while a run is active.

## Protocol (VM <-> laptop, over SSH — laptop always initiates, never listens)

`orchestrate.py` (VM side) writes a **decision request** file when a
checkpoint halts for review:

    checkpoints/greenhouse_run_<run_id>/checkpoint_<NNNN>.decision_request.json

```json
{
  "run_id": 15,
  "checkpoint_n": 2,
  "ats": "greenhouse",
  "report_path": "checkpoints/greenhouse_run_15/checkpoint_0002.md",
  "needs_human_decision": [{"category": "...", "reason": "...", "cluster_summary": "..."}],
  "unapplied_fixes": [{"category": "...", "reason": "gate_failed|guard_conflict", "gate_result": {...}}],
  "created_at": "2026-08-07T02:23:27Z"
}
```

This runner (laptop side) polls for that file over SSH (`db_state.py`-style
`FOR UPDATE SKIP LOCKED` isn't available here since it's a plain file, so
polling atomically renames the request file to `.claimed` before acting,
so a restarted runner never double-processes one), feeds its content plus
the full checkpoint report to the persistent per-ATS `claude` session, and
writes back:

    checkpoints/greenhouse_run_<run_id>/checkpoint_<NNNN>.decision_response.json

```json
{
  "checkpoint_n": 2,
  "decisions": [
    {"target": "cat_foo", "action": "apply_as_is|apply_with_edit|reject|escalate", "commit_sha": "...", "rationale": "..."},
    {"target": "new_category_bar", "action": "propose_only", "proposal_note": "...", "rationale": "..."}
  ],
  "resume_run": true,
  "decided_at": "2026-08-07T03:01:00Z"
}
```

`orchestrate.py`'s `poll_for_decision_response()` polls for
`.decision_response.json` (called from `harness_runner.py`'s checkpoint-halt
branch only when `--use-decision-agent` is passed) before resuming the run
loop. On timeout (laptop unreachable/asleep too long) or a response with
`resume_run: false`, falls back to the original hard-halt behavior.

## Files

- `runner.py` — main loop: poll VM over SSH, dispatch to `claude_session.py`, write response back. Entry point.
- `claude_session.py` — one persistent `claude -p --session-id <uuid> [--resume <uuid>]` subprocess per ATS. Builds the first-spawn briefing prompt (full context: FORM_ENGINE_DESIGN.md, decisions/*.md, hard file-write ceiling) and the per-checkpoint resume prompt (checkpoint report + corpus-grounding instructions).
- `ssh_bridge.py` — thin wrapper around `ssh`/`scp` subprocess calls to the VM. Outbound-only from the laptop; no inbound port opened.
- `sleep_guard.py` — Windows `SetThreadExecutionState` sleep-prevention, active only while the runner is alive.
- `config.py` — VM host/key path, poll interval, per-ATS session-id persistence file.
