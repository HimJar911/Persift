"""Block/anomaly detection for the harness — adapted from
pipeline/corpus_harvester.py's _looks_blocked()/_BLOCK_SIGNATURES, which are
reused verbatim (same regex, same signal) since the underlying page-level
block signature doesn't change for live form interaction vs. passive
scraping. The response logic is new: live interaction is a more aggressive
footprint than scraping, so per joyful-sprouting-swan.md's "Circuit breaker"
section, this starts at a lower streak threshold (10, vs. the harvester's 20)
and distinguishes two failure shapes that need different responses.

Public API:
    CircuitBreaker         — one instance per run, shared across workers
    looks_blocked(html, status)  — page-level block signature check
"""

import re


_BLOCK_SIGNATURES = re.compile(
    r"checking your browser before accessing|attention required.{0,40}cloudflare|"
    r"unusual traffic from your computer network|"
    r"complete the security check to continue|"
    r"access denied\s*<|"
    r"you have been blocked|request blocked by administrative rules|"
    # "verify you are a human" was the older Cloudflare interstitial
    # phrasing; live investigation of a real Bayada block (Aug 7) found
    # the current Cloudflare Turnstile copy is "Verify you are human" (no
    # "a") plus "Performing security verification" — added both without
    # removing the original, since the older phrasing may still appear on
    # non-Cloudflare or legacy-Cloudflare-config pages.
    r"verify you are a? ?human|performing security verification",
    re.IGNORECASE,
)

# Lower than corpus_harvester.py's 20 — live form interaction (clicking,
# typing, triggering React re-renders) is a much more aggressive footprint
# than passive HTML scraping, so per the plan's decision #7 ("start
# conservative"), this trips sooner.
_BLOCK_STREAK_THRESHOLD = 10

# Real bug found live (Aug 7): the original design halted on the FIRST
# page-block sighting, no streak needed. Once looks_blocked() actually
# worked correctly (a real fix -- see job_driver.py's status-check comment),
# this meant one Cloudflare-fronted domain (jobs.bayada.com) blocking a
# single job instantly killed a 99-job run with 98 jobs never attempted --
# the SAME job had succeeded in an earlier run, confirming the block was
# domain-specific/transient, not a broad "we're blocked everywhere" signal.
# Page-blocks now need their own (lower, since a real block is a stronger
# signal than a generic timeout/failure) streak before halting, same
# streak-not-first-sighting principle _BLOCK_STREAK_THRESHOLD already uses
# for outcome streaks -- distinguishes "one domain is Cloudflare-fronted"
# from "we are actually broadly blocked."
_PAGE_BLOCK_STREAK_THRESHOLD = 3

_STREAK_OUTCOMES = {"failed", "timeout", "harness_error"}
# no_job_available (added Aug 8 2026, migration 029) is a RESET outcome, not
# a streak one — it means the freshness check correctly found nothing to do
# for a dead listing, not that anything is broken. Treating a run of dead
# jobs as failure-streak noise would risk halting a perfectly healthy run.
_RESET_OUTCOMES = {"mechanically_verified", "needs_review_non_submit", "no_job_available"}

# If an outcome streak (no page-block signature seen) eats most of a
# checkpoint batch, force an early out-of-band checkpoint rather than waiting
# for the scheduled one — same "don't wait out a fixed count once you already
# know" reasoning the plan applies to checkpoint triggers generally.
_EARLY_CHECKPOINT_STREAK_FRACTION = 0.8


def looks_blocked(html: str, status: int | None) -> bool:
    if status is not None and status in (403, 429):
        return True
    return bool(_BLOCK_SIGNATURES.search(html[:5000]))


class CircuitBreaker:
    """Shared across all workers in a run — block_streak is a global smoke
    alarm, not per-worker, matching corpus_harvester.py's _SharedState
    reasoning: with N workers interleaving results across many different
    postings, a real streak of N-ish organic failures back-to-back is
    unremarkable on its own, but a longer streak regardless of which worker
    hit it is a real signal."""

    def __init__(self, checkpoint_every: int = 50, streak_threshold: int = _BLOCK_STREAK_THRESHOLD,
                 page_block_streak_threshold: int = _PAGE_BLOCK_STREAK_THRESHOLD) -> None:
        self.streak_threshold = streak_threshold
        self.page_block_streak_threshold = page_block_streak_threshold
        self.checkpoint_every = checkpoint_every
        self.block_streak = 0
        self.page_block_streak = 0
        self.page_block_tripped = False
        self.page_block_reason: str | None = None

    def record_page_block(self, reason: str) -> None:
        """A page-level block signature was seen directly (CAPTCHA/Cloudflare/
        etc.). Requires page_block_streak_threshold CONSECUTIVE sightings
        before tripping should_halt, not the first one -- see
        _PAGE_BLOCK_STREAK_THRESHOLD's comment for why (one blocked domain
        used to kill an entire run)."""
        self.page_block_streak += 1
        self.page_block_reason = reason
        if self.page_block_streak >= self.page_block_streak_threshold:
            self.page_block_tripped = True

    def record_outcome(self, outcome: str) -> None:
        if outcome in _STREAK_OUTCOMES:
            self.block_streak += 1
        elif outcome in _RESET_OUTCOMES:
            self.block_streak = 0
            self.page_block_streak = 0
        # skipped_blocked is neither — it's a consequence of an
        # already-tripped breaker, not new evidence either way. A
        # non-page-block failure (timeout/failed/harness_error) does NOT
        # reset page_block_streak -- only a real success does, since a
        # timeout right after a block could still be the same underlying
        # issue continuing.

    @property
    def should_halt(self) -> bool:
        """page_block_tripped only becomes True once record_page_block has
        seen page_block_streak_threshold CONSECUTIVE page-blocks (see that
        method) -- not on the first sighting. Outcome streak crossing the
        threshold also halts (the plan's Circuit Breaker section: an
        outcome streak with no page-block signature "flags loudly but lets
        the run continue to its next scheduled checkpoint, UNLESS the
        streak is most of a checkpoint batch" — that "most of a batch" case
        is handled by should_force_early_checkpoint, not halt; should_halt
        itself is reserved for a confirmed page-block streak or an outcome
        streak that has fully crossed the hard threshold)."""
        return self.page_block_tripped or self.block_streak >= self.streak_threshold

    @property
    def should_force_early_checkpoint(self) -> bool:
        """An outcome streak eating most (>=80%) of a checkpoint batch,
        without yet crossing the hard halt threshold — force an
        out-of-band checkpoint instead of waiting for the scheduled one."""
        if self.page_block_tripped:
            return False
        return self.block_streak >= int(_EARLY_CHECKPOINT_STREAK_FRACTION * self.checkpoint_every)

    def status_summary(self) -> dict:
        return {
            "block_streak": self.block_streak,
            "streak_threshold": self.streak_threshold,
            "page_block_streak": self.page_block_streak,
            "page_block_streak_threshold": self.page_block_streak_threshold,
            "page_block_tripped": self.page_block_tripped,
            "page_block_reason": self.page_block_reason,
            "should_halt": self.should_halt,
            "should_force_early_checkpoint": self.should_force_early_checkpoint,
        }
