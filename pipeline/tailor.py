"""Resume tailoring via OpenAI GPT-4o.

Returns structured JSON that maps directly to docx editing operations.
Falls back to plain-text output for the ReportLab fallback path.
"""

import asyncio
import json
import logging
from pathlib import Path

from openai import AsyncOpenAI, RateLimitError

import config
from config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

RESUME_DIR = Path(__file__).resolve().parent.parent / "resume"

SYSTEM_PROMPT = """\
You are an expert resume tailor. You receive a candidate's base resume and a job description. \
Your job is to make surgical, targeted changes to maximize relevance for the specific role.

STRICT RULES — VIOLATIONS ARE UNACCEPTABLE:

LENGTH:
- A tailored bullet must NEVER be longer than the original bullet it replaces. Count words. Shorter or equal only.
- If your tailored bullet would be longer, cut words until it is equal or shorter. No exceptions.
- If replacing bullets would cause the resume to overflow one page, return the original bullets unchanged for that section.

METRICS AND SPECIFICS — NEVER REMOVE:
- Every number, percentage, metric, or quantified result in the original MUST appear verbatim in the tailored version.
- "80%" must stay "80%". "<40 seconds" must stay "<40 seconds". "10K+" must stay "10K+". "50%" must stay "50%".
- Never replace specific technical details with vague words. "in <10 seconds" must NEVER become "swiftly" or "quickly". "LLM code analysis (50%)" must NEVER become "code analysis".
- Preserve "Fortune 500" if it appears in the original bullets.

BANNED PHRASES — never use any of these or anything similar:
"impacting production systems", "fostering collaboration", "supporting proactive feedback", \
"leveraging", "utilizing", "seamlessly", "robust", "driving impact", "cross-functional alignment", \
"stakeholder engagement", "value-add", "synergize", "streamlining operations", "aligning with", \
"in a fast-paced environment"

TECHNICAL DETAIL IS SACRED — these must never be removed or summarized:
- Specific percentages and numbers (80%, 65%, <40 seconds, <10 seconds, 90%)
- Specific technology names with context (LLM code analysis, Vision-based deployment checks, SSE streaming, Redis caching, request throttling)
- Specific architecture details (parallel verification agents, Bedrock knowledge base, AWS ECS Fargate)
- Weighted scoring breakdowns like (50%), (30%), (20%) — these must be preserved exactly

THE ONLY ACCEPTABLE CHANGES TO A BULLET ARE:
1. Swap the opening action verb for a stronger or more JD-relevant one
2. Add one specific keyword from the JD naturally into the middle of the bullet without removing anything
3. Reorder clauses within the bullet to lead with the most impressive outcome first
4. If none of these can be done without making the bullet longer or removing technical detail, return the original bullet unchanged
If you cannot improve a bullet within these constraints, return the original verbatim. \
A bullet that is technically weaker than the original is always worse than keeping the original \
even if it has more JD keywords.

CONTENT:
- Return ONLY valid JSON. No markdown, no backticks, no explanation outside the JSON.
- Always return exactly 3 bullets per experience role and exactly 3 bullets per project — no more, no less.
- Use the STAR method in every bullet: situation/task, action, result with a metric.
- Never add new sections or remove existing ones.
- Never change any names, dates, company names, job titles, project names, or links.
- Only change the text content of bullets.
- Do not fabricate metrics, accomplishments, or skills. Only rephrase existing content.
- The goal is to ADD or SWAP IN keywords from the job description naturally — not to rewrite or simplify.
- Preserve the candidate's voice and writing style.

SKILLS ADDITIONS:
- Identify specific technical keywords from the job description that are genuinely relevant to the candidate but missing from the Skills section.
- Only include real, legitimate skills — never fabricate.
- Categorize each addition into exactly one of: "Languages", "Frameworks & APIs", "Cloud & Infrastructure", "Databases", "Tools & Practices".
- If nothing needs adding, return an empty list.

SKILLS SWAPS:
- Surface skills the candidate genuinely has using the exact terminology the job description uses, and remove skills that add no signal for this specific role.
- ONLY add a skill if at least one of these is true:
  - The candidate already has it listed somewhere under a different name or abbreviation (e.g. JD says "CI/CD pipelines", candidate has "GitHub Actions" — add "CI/CD" using JD's exact phrasing)
  - The candidate's project descriptions or experience bullets directly demonstrate it even if not named (e.g. JD says "distributed systems", candidate built LoadAudit with concurrent workers and IncidentIQ on ECS Fargate — that IS distributed systems)
  - It is a category of technology the candidate clearly works in (e.g. JD says "REST APIs", candidate has FastAPI and built APIs — add it)
  - It is a tool in the same ecosystem as something they already have (e.g. candidate has AWS DynamoDB, JD emphasizes AWS broadly — surface specific AWS services they used)
- NEVER add a skill if:
  - The candidate has shown no evidence of it anywhere in their resume
  - It is a soft skill or attitude ("willingness to learn", "strong communicator", "team player")
  - It is a programming language they have not used in any project or role
  - It is a framework or tool with no connection to anything in their background
  - You are not confident it is genuine — when in doubt, leave it out
- Find skills currently in the resume that are low signal for this specific job (not mentioned in JD, not a core language, niche tool)
- Replace them with genuine skills identified above using the JD's exact terminology
- One out, one in — the skill line length stays roughly the same
- If no genuine swap exists for a category, do not force one — return an empty list
- Each swap must specify "category", "remove", and "add" fields

Return JSON with this exact shape:
{
  "experience": [
    {
      "company": "Johnson & Johnson (Contracted via Virtusa Corporation)",
      "bullets": ["bullet 1", "bullet 2", "bullet 3"]
    },
    {
      "company": "The Silicon Partners",
      "bullets": ["bullet 1", "bullet 2", "bullet 3"]
    }
  ],
  "projects": [
    {
      "name": "Shortlyst",
      "bullets": ["bullet 1", "bullet 2", "bullet 3"]
    },
    {
      "name": "IncidentIQ",
      "bullets": ["bullet 1", "bullet 2", "bullet 3"]
    },
    {
      "name": "LoadAudit",
      "bullets": ["bullet 1", "bullet 2", "bullet 3"]
    }
  ],
  "skills_additions": [
    {"category": "Frameworks & APIs", "skill": "GraphQL"},
    {"category": "Tools & Practices", "skill": "Terraform"}
  ],
  "skills_swaps": [
    {"category": "Frameworks & APIs", "remove": "SSE", "add": "REST APIs"},
    {"category": "Tools & Practices", "remove": "Playwright", "add": "Terraform"}
  ],
  "changes": [
    "description of change 1",
    "description of change 2"
  ]
}\
"""

# Module-level singleton — reuses connection pool across all tailor calls
_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _client


# Cache file reads — they don't change at runtime
_base_resume_cache: str | None = None
_ats_prompt_cache: dict[str, str] = {}


def _pdf_to_text(path: Path) -> str:
    """Extract plain text from a PDF using PyMuPDF."""
    import fitz  # pymupdf
    text_parts = []
    with fitz.open(str(path)) as doc:
        for page in doc:
            text_parts.append(page.get_text())
    return "\n".join(text_parts).strip()


def _load_base_resume() -> str:
    global _base_resume_cache
    if _base_resume_cache is None:
        pdf_path = RESUME_DIR / "base_resume.pdf"
        txt_path = RESUME_DIR / "base_resume.txt"

        if pdf_path.exists():
            logger.info("Loading resume from %s (PDF to plain text)", pdf_path.name)
            _base_resume_cache = _pdf_to_text(pdf_path)
            txt_path.write_text(_base_resume_cache, encoding="utf-8")
            logger.info("Extracted text saved to %s for review", txt_path.name)
        else:
            _base_resume_cache = txt_path.read_text(encoding="utf-8")

    return _base_resume_cache


def _load_ats_prompt(ats: str) -> str:
    if ats not in _ats_prompt_cache:
        path = RESUME_DIR / "ats_prompts" / f"{ats}.txt"
        _ats_prompt_cache[ats] = path.read_text(encoding="utf-8") if path.exists() else ""
    return _ats_prompt_cache[ats]


def _build_user_message(job: dict, base_resume: str, ats_rules: str) -> str:
    return (
        f"ATS PLATFORM: {job['ats']}\n\n"
        f"ATS-SPECIFIC RULES:\n{ats_rules}\n\n"
        f"JOB DESCRIPTION:\n{job['description_plain_text']}\n\n"
        f"COMPANY: {job['company_name']}\n"
        f"ROLE: {job['title']}\n\n"
        f"MY BASE RESUME:\n{base_resume}\n\n"
        "Tailor my resume for this role. Return ONLY the JSON object described in your instructions."
    )


def _parse_json_response(text: str) -> dict | None:
    """Try to parse the LLM response as JSON. Returns None on failure."""
    # Strip markdown fences if the model wraps them despite instructions
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Remove opening fence line
        first_newline = cleaned.index("\n")
        cleaned = cleaned[first_newline + 1:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
        # Basic validation
        if "experience" in data and "projects" in data and "changes" in data:
            return data
        logger.warning("JSON response missing required keys")
        return None
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Failed to parse JSON response: %s", exc)
        return None


def _build_plain_text_from_json(data: dict, base_resume: str) -> str:
    """Build a plain-text resume from the JSON for the ReportLab fallback."""
    lines = []
    # Use the base resume header (everything before EXPERIENCE)
    if "EXPERIENCE" in base_resume:
        lines.append(base_resume.split("EXPERIENCE")[0].strip())
    else:
        lines.append(base_resume[:500])

    lines.append("\nEXPERIENCE")
    for exp in data.get("experience", []):
        lines.append(f"\n{exp['company']}")
        for b in exp.get("bullets", []):
            lines.append(f"● {b}")

    lines.append("\nPROJECTS")
    for proj in data.get("projects", []):
        lines.append(f"\n{proj['name']}")
        for b in proj.get("bullets", []):
            lines.append(f"● {b}")

    return "\n".join(lines)


def format_changes_for_slack(data: dict) -> str:
    """Format the changes list for Slack notification."""
    changes = data.get("changes", [])
    if not changes:
        return "(No changes listed)"
    return "\n".join(f"• {c}" for c in changes)


_MAX_RETRIES = 4
_RETRY_DELAYS = [15, 30, 60, 120]  # seconds — escalating backoff for 429s


async def tailor_resume(job: dict) -> tuple[dict | None, str]:
    """Call OpenAI to tailor the resume. Returns (tailoring_data, changes_text).

    tailoring_data is the parsed JSON dict, or None if parsing failed
    (caller should fall back to ReportLab with changes_text).
    """
    logger.info("Tailoring resume for %s at %s", job["title"], job["company_name"])

    base_resume = _load_base_resume()
    ats_rules = _load_ats_prompt(job["ats"])
    user_msg = _build_user_message(job, base_resume, ats_rules)

    client = _get_client()

    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = await client.chat.completions.create(
                model=config.OPENAI_MODEL,
                max_tokens=config.OPENAI_MAX_TOKENS,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
            )
            break
        except RateLimitError:
            if attempt == _MAX_RETRIES:
                logger.error(
                    "Rate limit exhausted after %d retries for %s at %s",
                    _MAX_RETRIES, job["title"], job["company_name"],
                )
                raise
            delay = _RETRY_DELAYS[attempt]
            logger.warning(
                "Rate limited (attempt %d/%d) for %s — retrying in %ds",
                attempt + 1, _MAX_RETRIES, job["company_name"], delay,
            )
            await asyncio.sleep(delay)

    if not response.choices:
        logger.warning(
            "OpenAI returned empty choices for %s at %s — possible content filter",
            job["title"], job["company_name"],
        )
        return None, "OpenAI returned empty response — possible content filter"

    response_text = response.choices[0].message.content
    data = _parse_json_response(response_text)

    if data is not None:
        changes_text = format_changes_for_slack(data)
        logger.info("Resume tailored (JSON) for %s", job["company_name"])
        return data, changes_text

    # JSON parse failed — return None so caller uses ReportLab fallback
    logger.warning("JSON parse failed for %s — returning raw text for fallback", job["company_name"])
    return None, response_text
