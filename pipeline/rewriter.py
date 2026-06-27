"""Layer 4 LLM resume rewriter — OpenAI API (gpt-4o).

Two-part prompt in a single API call:
  Part 1: identify the 3-5 weakest bullets relative to the JD
  Part 2: rewrite only those bullets to mirror JD language and missing keywords

Falls back to returning the original resume text unchanged on any API or parse error.

Single public function: rewrite_resume(resume_text, jd_text, keyword_match_data) -> str
"""

import json
import logging
import re

from openai import OpenAI, OpenAIError

from config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

_MODEL      = "gpt-4o"
_MAX_TOKENS = 1000

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


_SYSTEM = (
    "You are a professional resume editor. You identify weak bullets and rewrite them "
    "to match a job description. You respond only with valid JSON — no markdown, no explanation."
)


def _build_prompt(
    resume_text: str,
    jd_text: str,
    missing: list[str],
    present: list[str],
) -> str:
    missing_str = ", ".join(missing) if missing else "none"
    present_str = ", ".join(present[:20]) if present else "none"
    return f"""\
Analyze the resume against the job description in two steps.

**Step 1 — Identify weak bullets**
Find the 3-5 weakest bullets. A weak bullet is one that:
- Is vague with no concrete outcome or metric
- Does not mirror the language or priorities of the JD
- Could apply to any company or role

**Step 2 — Rewrite only those bullets**
Rewrite each identified bullet to:
- Mirror the JD's terminology and priorities
- Incorporate missing keywords naturally where relevant: {missing_str}
- Add plausible metrics where context implies them (e.g. "large dataset" → "10M+ record dataset")
- Keep approximately the same length as the original

Return ONLY a JSON object in this exact format:
{{
  "weak_bullets": ["exact original bullet text", ...],
  "rewrites": {{
    "exact original bullet text": "rewritten bullet text",
    ...
  }}
}}

JOB DESCRIPTION:
{jd_text}

RESUME:
{resume_text}

Keywords already present in resume (do not force): {present_str}
Missing keywords to incorporate naturally: {missing_str}
"""


def _extract_json(text: str) -> dict:
    """Extract the first JSON object from the model response."""
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`")
    start = text.find("{")
    end   = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("No JSON object found in response")
    return json.loads(text[start:end])


def _apply_rewrites(resume_text: str, rewrites: dict[str, str]) -> tuple[str, int]:
    """Replace original bullets with rewrites. Returns (modified_text, applied_count)."""
    result  = resume_text
    applied = 0
    for original, rewritten in rewrites.items():
        if original in result:
            result  = result.replace(original, rewritten, 1)
            applied += 1
        else:
            # Strip leading bullet characters and retry with a regex
            stripped = original.lstrip("-•*– ").strip()
            pattern  = re.compile(
                r"(^[\s\-•*–]+)" + re.escape(stripped),
                re.MULTILINE,
            )
            m = pattern.search(result)
            if m:
                result  = result[: m.start()] + m.group(1) + rewritten + result[m.end():]
                applied += 1
            else:
                logger.debug("Could not locate bullet in resume: %r", original[:80])
    return result, applied


def rewrite_resume(resume_text: str, jd_text: str, keyword_match_data: dict) -> str:
    """Rewrite the weakest resume bullets to better match the JD.

    Returns the modified resume, or the original unchanged on any error.
    """
    if not OPENAI_API_KEY:
        logger.warning("Layer 4 disabled: OPENAI_API_KEY not set — returning original resume unchanged")
        return resume_text

    missing = keyword_match_data.get("missing", [])
    present = keyword_match_data.get("present", [])

    try:
        # TODO: swap to Claude API (claude-sonnet-4-6) when credits available — 3-line change: replace openai client init, model name, and response parsing
        response = _get_client().chat.completions.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user",   "content": _build_prompt(resume_text, jd_text, missing, present)},
            ],
        )
        response_text = response.choices[0].message.content or ""
    except OpenAIError as exc:
        logger.error("OpenAI API call failed: %s", exc)
        return resume_text

    try:
        data     = _extract_json(response_text)
        rewrites = data.get("rewrites", {})
    except (ValueError, json.JSONDecodeError) as exc:
        logger.error("Failed to parse rewriter response as JSON: %s", exc)
        return resume_text

    if not rewrites:
        logger.warning("Rewriter returned no rewrites — returning resume unchanged")
        return resume_text

    result, applied = _apply_rewrites(resume_text, rewrites)
    logger.info("Rewriter: %d/%d bullets applied", applied, len(rewrites))
    return result
