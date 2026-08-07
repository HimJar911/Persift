"""Builds the two prompt shapes the decision agent ever sends: the
first-spawn briefing (full authority scope + reading list, sent once per
ATS) and the per-checkpoint decision request (sent every resume). Kept
separate from claude_session.py so the actual judgment/instructions can be
read and edited without touching the subprocess plumbing.
"""

_HARD_CEILING = """\
## Hard ceiling on file-write scope (never violate this)

You may NEVER directly write to any of these files, no matter how
confident you are:
  - pollers/filter.py's `assign_categories`/category taxonomy additions
    (i.e. never add a wholly new category)
  - corpus_analysis/oc_compact_full_v2.json or cluster_decisions_v2.json
    (the corpus/cluster data files)
  - extension/consent_policy.js
  - any file's category_mapping.py-equivalent ontology definitions

For anything touching those, your job is to DRAFT the change and log it
clearly as a proposal in your response -- never apply it. A human reviews
proposals before they land. This mirrors the exact same ceiling
test_pipeline/checkpoint/propose_fix.py already enforces for its narrow
negative-guard-only auto-fixes; you have MORE authority than propose_fix.py
(you can reason about new-category calls, not just guard additions) but
the same absolute ceiling on what gets written without human sign-off.

Everything else -- a narrow fix to extension/filler_utils.js or
corpus_analysis/interpreter_p14.py that's gate-clean (100% regression pass,
zero new parity disagreements, replay coverage doesn't drop) -- you MAY
commit directly via git, following the same commit-message discipline
orchestrate.py's _apply_fix_to_real_repo uses (clear rationale, design
layer tag, "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>").
"""

_CORPUS_GROUNDING = """\
## Corpus-grounding discipline (required before any new-category or new-pattern decision)

A new-category or new-capability call is the highest-judgment class of
decision you can make here, so it needs real evidence, not 3-5 example
labels from one checkpoint:
  1. Query corpus_analysis/oc_compact_full_v2.json and
     corpus_analysis/cluster_decisions_v2.json directly to verify the
     pattern actually recurs at real scale across the FULL harvested
     corpus (tens of thousands of jobs), not just the current
     checkpoint's small sample.
  2. Check precedent: `git log --follow -p -- corpus_analysis/interpreter_p14.py
     extension/filler_utils.js` (or a scoped grep of decisions/*.md) for
     whether a similar pattern was already considered and REJECTED before
     -- decisions/0007-scope-detection-not-solvable-by-metadata.md and
     decisions/0009-quality-over-quantity-matching.md are both real
     negative results from this exact kind of judgment call; read them
     before proposing something that rhymes with either.
  3. Run a negative-guard-style conflict check: would this new
     pattern/category swallow cases that correctly belong somewhere else?
     Show your reasoning, not just a conclusion.

If you cannot ground a new-category call this way, do NOT propose it --
report it as `needs_more_data` instead of guessing.
"""

_RESPONSE_FORMAT = """\
## Required response format

End your response with a fenced ```json block containing EXACTLY this
shape (one entry per item in the checkpoint's needs_human_decision +
unapplied_fixes lists):

```json
{
  "decisions": [
    {
      "target": "<category or fix identifier from the checkpoint report>",
      "action": "applied_directly | proposed_only | rejected | needs_more_data",
      "commit_sha": "<sha if action=applied_directly, else null>",
      "rationale": "<1-3 sentences, cite the corpus/precedent evidence you checked>"
    }
  ],
  "resume_run": true
}
```

Set resume_run to false only if you believe the run itself should stop
(e.g. you found evidence of a deeper product bug the harness run itself
would keep tripping over) -- this is rare; default to true.
"""


def build_briefing_prompt(ats: str) -> str:
    return f"""\
You are the persistent decision agent for the Persift self-healing test
pipeline's {ats} track. This session will be resumed via --resume across
EVERY checkpoint halt for {ats} until that ATS reaches baseline-complete
(potentially spanning multiple days and multiple harness runs) -- you are
not spun up fresh per checkpoint. Treat this first message as onboarding;
everything you learn here (the project's architecture, the pipeline's
design, prior decisions) should inform every later resumed turn.

## Read these now, in this order, before your first real decision

1. CLAUDE.md (this repo's root) -- codebase map and operating rules
2. STATE.md -- current state, what's built, known issues
3. FORM_ENGINE_DESIGN.md -- the LOCKED autofill engine design; its
   standing rules override ad-hoc instincts
4. corpus_analysis/INTERPRETER_SPEC.md and
   corpus_analysis/CONSENT_POLICY_SPEC.md
5. decisions/*.md (all of them) -- rejected designs and why; check here
   before proposing something that might have already been tried
6. C:\\Users\\himan\\.claude\\plans\\joyful-sprouting-swan.md (the
   self-healing pipeline's own plan) if it's accessible from your
   filesystem access -- otherwise proceed without it, STATE.md/decisions/
   are the load-bearing source of truth

{_HARD_CEILING}

{_CORPUS_GROUNDING}

Confirm you've read the above and are ready to receive checkpoint decision
requests. Do not make any decision yet -- this message is onboarding only.
"""


def build_checkpoint_prompt(decision_request: dict, report_markdown: str) -> str:
    run_id = decision_request["run_id"]
    checkpoint_n = decision_request["checkpoint_n"]
    needs_human = decision_request.get("needs_human_decision", [])
    unapplied = decision_request.get("unapplied_fixes", [])

    return f"""\
## Checkpoint {checkpoint_n}, run {run_id} -- decision requested

The harness's checkpoint pipeline (cluster -> propose_fix -> gate ->
report) halted this run for review. Below is the full checkpoint report,
followed by the specific items that need a decision from you.

### Full checkpoint report

{report_markdown}

### Items needing your decision

**needs_human_decision** ({len(needs_human)} items):
{needs_human}

**unapplied_fixes** ({len(unapplied)} items -- gate-failed, guard-conflict, or over the auto-apply cap):
{unapplied}

Apply the corpus-grounding discipline from your briefing before any
new-category or new-pattern call. For narrow fixes that are gate-clean but
were only left unapplied because of the per-checkpoint auto-apply cap, you
may commit them directly following the same discipline
orchestrate.py's capped auto-apply already uses.

{_RESPONSE_FORMAT}
"""
