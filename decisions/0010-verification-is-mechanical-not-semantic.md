# 0010 — `isInputFilled()` verification is mechanical, not semantic; `verified: true` does not imply the filled value was correct

**Date:** 2026-08-02
**Status:** acknowledged, deliberately deferred — future work, don't lose this
**Files:** `extension/filler_utils.js` (`isInputFilled`, `runPass`, `retryFill`)

## Context

P1.5 added verify/retry (`FORM_ENGINE_DESIGN.md` §3.4): after `fillField()`
reports success, `isInputFilled(field.el)` re-checks the actual DOM state,
because React re-renders can silently revert a write without erroring.
This closed a real gap — a fill mechanism returning `true` only ever meant
"ran without throwing," not "the value actually landed."

The first live browser test after P1.5 (Myriad360, job `8646163002`)
surfaced a real classification bug: a "preferred name/nickname... phonetic
pronunciation" field was misclassified `phone` (fixed — see
`corpus_analysis/interpreter_regressions.json`'s last entry) and filled
with the user's phone number. That field's fill mechanism succeeded and
`isInputFilled()` correctly reported `true` — the log read `filler: filled
(verified)`. The verification passed. The answer was wrong.

## The gap

`isInputFilled()` (and by extension the whole verify/retry mechanism) only
answers "did *a* value land in this field's DOM element." It has no way to
answer "is that the *correct* value for what this field is actually
asking." These are different questions:

```
classified correctly?  fill succeeds?  isInputFilled()?  → what "verified" means today
      wrong                 yes              true          "verified", but WRONG ANSWER
      correct               yes              true          verified, correct
      correct                no              false          correctly reported as failed
```

The system's own metrics (`filler: filled (verified)` in the console
today; `verified` as a field, if/when telemetry — P2.3 — persists this)
cannot currently distinguish the first row from the second. A
misclassification that happens to have a resolvable profile value is
indistinguishable, from the log/metric alone, from a correct fill. This is
a systemic blind spot in what "verified" proves, not a one-off bug —
every future classification error with a resolvable value will look
identical to a correct fill unless this is addressed.

## Decision

Not fixed now. Acknowledged and recorded here, per the same discipline as
[0008](0008-corpus-harvester-scale-and-scope-gap.md) (flag a real deferred
concern so it can't silently disappear once the immediate task is done),
rather than left as an inline code comment that dies with whichever PR
introduced it.

**Likely shape when picked up** (not designed in detail here — this ADR's
job is to record the gap, not solve it):
- **Read-back + cross-check**: after a fill, re-read the actual DOM value
  and compare it against what `resolveValue()` intended to write, catching
  cases where the write mechanism itself altered/truncated/mismatched the
  value — narrower than semantic verification, but closes part of the gap
  cheaply.
- **Real semantic verification**: would need either a second, independent
  classification pass to cross-check agreement (expensive, and doesn't
  solve the case where both passes share the same underlying bug), or
  human review — sampled or full, likely gated by confidence tier once
  confidence calibration exists (`FORM_ENGINE_DESIGN.md` §3.6, "Later —
  confidence calibration," itself still gated on live telemetry that
  doesn't exist yet).
- **field_corrections** (migration 015, capture not yet built, rides P2.3)
  is the actual long-term answer for this at scale — a user's real
  correction to a wrong fill IS the semantic ground truth this ADR is
  missing. This decision doesn't change that plan; it just makes explicit
  that until `field_corrections` capture exists, there is no signal in the
  system today that can catch this class of error.

## Not a reason to distrust today's `verified` numbers wholesale

This isn't a claim that verify/retry is useless — it correctly catches the
class of failure it was built for (silent write-reverts), and the P1.5
live test confirmed that mechanism works (`DOM_LISTBOX_NEVER_OPENED` and
similar reasons now surface real, specific causes, see
`corpus_analysis/README.md`'s P1.5/live-test-fixes section). The point is
narrower: `verified: true` is *necessary* evidence a value was written,
not *sufficient* evidence it was the right one. Read it that way.
