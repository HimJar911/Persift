"""Layer 3 keyword injection — pure Python, no LLM.

Filters missing keywords down to technical terms and appends them to the
Skills section of a resume. Falls back to appending a new Skills section
if none is found.

Single public function: inject_keywords(resume_text, missing_keywords) -> str
"""

import re

# Keywords that identify a skills section header
_SKILLS_HEADERS = ("skills", "technologies", "tech stack", "tools", "technical skills")

# Keywords that identify the start of a different resume section
_OTHER_SECTIONS = frozenset({
    "experience", "education", "work history", "employment", "projects",
    "certifications", "awards", "publications", "interests", "volunteer",
    "objective", "summary", "profile", "achievements", "languages",
    "hobbies", "references", "activities",
})

# Token suffixes that signal a technical term
_TECH_SUFFIXES = frozenset({"js", "py", "sql", "api", "sdk", "cli", "css", "ml", "ai", "db"})

# Common technologies that don't match suffix/digit/hyphen heuristics
_KNOWN_TECH = frozenset({
    "docker", "kubernetes", "postgres", "postgresql", "redis", "nginx",
    "terraform", "ansible", "linux", "ubuntu", "debian", "jenkins",
    "grafana", "prometheus", "hadoop", "spark", "kafka", "airflow",
    "tableau", "figma", "sketch", "jira", "confluence", "github",
    "gitlab", "bitbucket", "heroku", "vercel", "netlify", "firebase",
    "mongodb", "elasticsearch", "rabbitmq", "celery", "flask", "django",
    "fastapi", "pytorch", "tensorflow", "numpy", "pandas", "scipy",
    "matplotlib", "scrapy", "selenium", "playwright",
})


def _is_technical_term(token: str) -> bool:
    """Return True if the token looks like a technology or skill."""
    # Explicit known-tech list (checked first — fastest path for common cases)
    if token.lower() in _KNOWN_TECH:
        return True
    # Hyphenated compound: machine-learning, ci-cd, full-stack
    if "-" in token:
        return True
    # All-caps acronym: AWS, API, ML (≥ 2 chars)
    if token.isupper() and len(token) >= 2:
        return True
    # Contains a digit: python3, ec2, gpt4, s3
    if any(c.isdigit() for c in token):
        return True
    lower = token.lower()
    # Is itself a recognised tech suffix: sql, api, cli …
    if lower in _TECH_SUFFIXES:
        return True
    # Ends with a tech suffix: fastapi, nosql, graphql, devops
    for suffix in _TECH_SUFFIXES:
        if lower.endswith(suffix) and len(lower) > len(suffix):
            return True
    return False


def _is_skills_header(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 80:
        return False
    lower = stripped.lower()
    return any(h in lower for h in _SKILLS_HEADERS)


def _is_other_section_header(line: str) -> bool:
    """Heuristic: short line that names a different resume section."""
    stripped = line.strip()
    if not stripped or len(stripped) > 80:
        return False
    lower = stripped.lower().rstrip(":- ")
    return any(kw in lower for kw in _OTHER_SECTIONS)


def inject_keywords(resume_text: str, missing_keywords: list[str]) -> str:
    """Append filtered missing keywords to the Skills section of resume_text.

    Returns the modified resume text unchanged if no technical terms remain
    after filtering.
    """
    tech_terms = [kw for kw in missing_keywords if _is_technical_term(kw)]
    if not tech_terms:
        return resume_text

    lines = resume_text.splitlines()

    # Locate the skills section header
    skills_idx: int | None = None
    for i, line in enumerate(lines):
        if _is_skills_header(line):
            skills_idx = i
            break

    suffix = ", ".join(tech_terms)

    if skills_idx is None:
        # No skills section found — append one at the end
        return resume_text.rstrip() + f"\n\nSkills\n{suffix}\n"

    # Find where the skills section ends (next non-skills section header)
    section_end = len(lines)
    for i in range(skills_idx + 1, len(lines)):
        if _is_other_section_header(lines[i]):
            section_end = i
            break

    # Check for inline content on the header line itself: "Skills: Python, Java"
    header = lines[skills_idx]
    if ":" in header and header.split(":", 1)[1].strip():
        lines[skills_idx] = header.rstrip() + ", " + suffix
        return "\n".join(lines)

    # Find the last non-empty content line within the skills section
    last_content = None
    for i in range(skills_idx + 1, section_end):
        if lines[i].strip():
            last_content = i

    if last_content is None:
        # Header only — insert a content line immediately after it
        lines.insert(skills_idx + 1, suffix)
    else:
        existing = lines[last_content].rstrip()
        sep = ", " if not existing.endswith(",") else " "
        lines[last_content] = existing + sep + suffix

    return "\n".join(lines)
