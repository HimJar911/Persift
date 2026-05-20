"""Resume scoring utilities.

extract_keywords — pure-Python keyword extraction from job descriptions.
score_resume     — cosine similarity + keyword presence check.
"""

import re

_STOPWORDS = frozenset({
    # Articles / conjunctions / prepositions
    "the", "and", "for", "but", "not", "all", "any", "can", "had", "her",
    "was", "one", "our", "out", "get", "has", "him", "his", "how", "its",
    "may", "new", "now", "old", "see", "two", "way", "who", "did", "let",
    "put", "say", "she", "too", "use", "with", "that", "this", "from",
    "have", "will", "been", "they", "were", "what", "when", "your", "more",
    "also", "some", "than", "then", "into", "over", "such", "make", "like",
    "time", "just", "know", "take", "good", "much", "need", "even", "most",
    "well", "only", "very", "able", "back", "each", "must", "high", "long",
    "down", "both", "help", "give", "used", "here", "every", "those",
    "these", "other", "would", "their", "there", "which", "about", "after",
    "where", "while", "could", "should", "through", "during", "before",
    "within", "between", "using", "based", "across", "without", "including",
    # JD filler
    "role", "team", "join", "position", "looking", "seeking", "candidate",
    "responsibilities", "requirements", "qualifications", "required",
    "preferred", "strong", "excellent", "great", "ideal", "background",
    "ability", "skills", "knowledge", "understanding", "familiarity",
    "proficiency", "comfortable", "proven", "demonstrated", "exposure",
    "plus", "bonus", "nice", "minimum", "least", "years", "year", "months",
    "month", "hands", "work", "working", "experience", "related", "relevant",
    "equivalent", "similar", "following", "including", "etc", "e.g", "i.e",
})

# Matches whole words and hyphenated compound terms (e.g. "machine-learning", "full-stack")
_TOKEN_RE = re.compile(r'[a-z][a-z0-9]*(?:-[a-z][a-z0-9]+)*')

_model = None  # SentenceTransformer, lazy-loaded on first call to score_resume


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def extract_keywords(text: str) -> list[str]:
    """Extract meaningful keywords from text.

    Keeps alphanumeric tokens and hyphenated compound terms longer than 2
    characters that are not in the stopword list. Returns lowercase, deduped,
    in order of first appearance.
    """
    tokens = _TOKEN_RE.findall(text.lower())
    seen: set[str] = set()
    result: list[str] = []
    for token in tokens:
        if len(token) > 2 and token not in _STOPWORDS and token not in seen:
            seen.add(token)
            result.append(token)
    return result


def _keyword_in_text(keyword: str, text_lower: str) -> bool:
    if keyword in text_lower:
        return True
    # also accept space-separated form of hyphenated keywords
    if "-" in keyword and keyword.replace("-", " ") in text_lower:
        return True
    return False


def score_resume(resume_text: str, jd_text: str) -> dict:
    """Score a resume against a job description.

    Returns:
        relevance_score  — 0-100 int (cosine similarity via all-MiniLM-L6-v2)
        present_keywords — JD keywords found in the resume
        missing_keywords — JD keywords absent from the resume
    """
    from sentence_transformers import util

    model = _get_model()
    resume_emb, jd_emb = model.encode([resume_text, jd_text])
    cosine = util.cos_sim(resume_emb, jd_emb).item()
    relevance_score = round(max(0.0, cosine) * 100)

    jd_keywords = extract_keywords(jd_text)
    resume_lower = resume_text.lower()

    present_keywords = [kw for kw in jd_keywords if     _keyword_in_text(kw, resume_lower)]
    missing_keywords = [kw for kw in jd_keywords if not _keyword_in_text(kw, resume_lower)]

    return {
        "relevance_score":  relevance_score,
        "present_keywords": present_keywords,
        "missing_keywords": missing_keywords,
    }
