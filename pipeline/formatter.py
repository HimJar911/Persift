"""Layer 5 — ATS formatting check.

Pure Python, $0 cost. Runs after Layer 4 (or after Layer 3 for score 50-79 users)
and before status is set to 'applying'. Non-blocking: issues are logged and stored
but never prevent advancement to 'applying'.

Single public function: check_ats_format(resume_text) -> {"passed": bool, "issues": list[str]}

Migration SQL (run once against Postgres before deploying):
    ALTER TABLE user_jobs
        ADD COLUMN IF NOT EXISTS ats_format_issues JSONB NOT NULL DEFAULT '[]';
"""

import re

_STANDARD_SECTIONS = frozenset([
    "experience", "education", "skills", "projects",
    "summary", "objective", "certifications", "awards",
])

_PAGE_NUM_RE = re.compile(r"\bpage\s+\d+\s+of\s+\d+\b", re.IGNORECASE)
_DASH_PAGE_RE = re.compile(r"^\s*-\s*\d+\s*-\s*$")
_MULTI_TAB_RE = re.compile(r"\S.*\t{2,}.*\S")


def check_ats_format(resume_text: str) -> dict:
    """Check resume text for ATS-hostile formatting patterns.

    Returns {"passed": bool, "issues": list[str]}.
    """
    issues: list[str] = []
    lines = resume_text.splitlines()

    # 1. Reasonable length
    word_count = len(resume_text.split())
    if word_count < 200:
        issues.append(
            f"Resume too sparse ({word_count} words; expected ≥200 for an intern resume)"
        )
    elif word_count > 1200:
        issues.append(
            f"Resume too long ({word_count} words; expected ≤1200 for an intern resume)"
        )

    # 2. Standard section headers — must contain at least 3
    text_lower = resume_text.lower()
    found_sections = {s for s in _STANDARD_SECTIONS if s in text_lower}
    if len(found_sections) < 3:
        missing = sorted(_STANDARD_SECTIONS - found_sections)
        issues.append(
            f"Only {len(found_sections)} standard section header(s) found (need ≥3); "
            f"missing: {', '.join(missing)}"
        )

    # 3. Single-column check — two chunks of text on the same line separated by 2+ tabs
    for line in lines:
        if _MULTI_TAB_RE.search(line):
            issues.append(
                "Multi-column layout detected: tab-separated columns on same line"
            )
            break

    # 4. Table detection — multiple pipe characters suggest markdown/ASCII tables
    for line in lines:
        if line.count("|") >= 2:
            issues.append(
                "Table detected: pipe characters suggest markdown or ASCII table"
            )
            break

    # 5. Page numbers in headers/footers — e.g. "Page 1 of 2" or "- 1 -"
    for line in lines:
        if _PAGE_NUM_RE.search(line) or _DASH_PAGE_RE.match(line):
            issues.append("Page number detected in header or footer")
            break

    return {"passed": len(issues) == 0, "issues": issues}
