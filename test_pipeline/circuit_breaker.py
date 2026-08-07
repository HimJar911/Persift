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

_STREAK_OUTCOMES = {"failed", "timeout", "harness_error"}
_RESET_OUTCOMES = {"mechanically_verified", "needs_review_non_submit"}

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

    def __init__(self, checkpoint_every: int = 50, streak_threshold: int = _BLOCK_STREAK_THRESHOLD) -> None:
        self.streak_threshold = streak_threshold
        self.checkpoint_every = checkpoint_every
        self.block_streak = 0
        self.page_block_tripped = False
        self.page_block_reason: str | None = None

    def record_page_block(self, reason: str) -> None:
        """A page-level block signature was seen directly (CAPTCHA/Cloudflare/
        etc.) — halt immediately, distinct from an outcome streak."""
        self.page_block_tripped = True
        self.page_block_reason = reason

    def record_outcome(self, outcome: str) -> None:
        if outcome in _STREAK_OUTCOMES:
            self.block_streak += 1
        elif outcome in _RESET_OUTCOMES:
            self.block_streak = 0
        # skipped_blocked is neither — it's a consequence of an
        # already-tripped breaker, not new evidence either way.

    @property
    def should_halt(self) -> bool:
        """Page-level block signature -> halt immediately. Outcome streak
        crossing the threshold -> also halt (the plan's Circuit Breaker
        section: an outcome streak with no page-block signature "flags
        loudly but lets the run continue to its next scheduled checkpoint,
        UNLESS the streak is most of a checkpoint batch" — that "most of a
        batch" case is handled by should_force_early_checkpoint, not halt;
        should_halt itself is reserved for a confirmed page-block or a
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
            "page_block_tripped": self.page_block_tripped,
            "page_block_reason": self.page_block_reason,
            "should_halt": self.should_halt,
            "should_force_early_checkpoint": self.should_force_early_checkpoint,
        }
