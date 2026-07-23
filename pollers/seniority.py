"""Literal years-of-experience extraction — no inference, ever.

Replaces the old is_intern_role() drop gate (deleted — see migration 022's
header comment) and an earlier, since-rejected design in this same file that
classified jobs into a categorical seniority_level enum (intern/entry_level/
mid_level/senior_level/executive/...). That design was killed before it
shipped: real employer-declared ground truth (SmartRecruiters'
experienceLevel on 124 real "Director"-titled jobs) showed the split was
50% executive / 24% mid_level / 24% entry-or-not_applicable — proof that
even the ATS's own label is genuinely ambiguous for a large class of
real titles, so any classifier guessing one bucket from title/description
alone would be confidently wrong on roughly half of them.

The replacement principle: only store what a job posting LITERALLY states.
No inference from tone, scope, responsibilities, or reporting structure —
if the posting doesn't spell out a number, the job gets NULL on both
years_of_experience_min/max and is matched on everything else it does
carry (category, location, work_model, sponsorship). NULL means "not
stated," never "unknown, guess something."

This module extracts ONLY the mechanical, zero-judgment case: an explicit
"N years" / "N+ years" / "N-M years" (of experience) phrase, wherever it
appears in the title or description. It is regex extraction over literal
text, not classification — there is no ambiguity in reading a number that
is actually printed on the page. Real bulk measurement (Jul 21, 2026,
~2,700 real Ashby/Greenhouse jobs with real description text): only 38.9%
of postings state a number this way. That's expected and fine — the other
61% simply carry no signal on this axis, which is the honest state, not a
gap to paper over with a guess.
"""

import re

_YOE_PATTERN = re.compile(
    r"(?P<min>\d{1,2})\s*(?:-|to|–|—)\s*(?P<max>\d{1,2})\s*\+?\s*years?\s+"
    r"(?:of\s+)?(?:relevant\s+|professional\s+|industry\s+|work(?:ing)?\s+)?experience"
    r"|"
    r"(?P<min_only>\d{1,2})\s*\+?\s*years?\s+"
    r"(?:of\s+)?(?:relevant\s+|professional\s+|industry\s+|work(?:ing)?\s+)?experience",
    re.IGNORECASE,
)


def extract_years_of_experience(*texts: str | None) -> tuple[int | None, int | None]:
    """Scan title/description text for an explicit "N years of experience"
    (or "N-M years of experience") phrase. Returns (min, max) — max is None
    for a bare "N+ years" / "N years" phrase (open-ended or exact), both are
    None if no such phrase is found anywhere in the given texts.

    Only the FIRST match found (scanning texts in the given order) is used —
    a posting stating multiple different experience requirements for
    different aspects of the role is real but rare, and picking the first
    literal statement is simpler and more predictable than trying to decide
    which one is "the" seniority requirement (that would be judgment, which
    this module exists to avoid).
    """
    for text in texts:
        if not text:
            continue
        m = _YOE_PATTERN.search(text)
        if not m:
            continue
        if m.group("min") is not None:
            return int(m.group("min")), int(m.group("max"))
        return int(m.group("min_only")), None
    return None, None
