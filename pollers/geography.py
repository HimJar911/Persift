"""Country normalization for ATS-provided location metadata.

SmartRecruiters and Lever return a clean, already-normalized ISO-2 country
code (confirmed via a live full-population census of every tracked company,
Jul 23 2026 — e.g. SmartRecruiters: 'us'/'fr'/'gb'/'de'/...; Lever: 'US'/'GB'/
'JP'/...). Both are stored as-is, just upper-cased for consistency.

Ashby returns a free-text country name that is NOT consistently formatted
across companies — confirmed via the same live census (9,497 jobs across
280 companies): the US alone appears as 'United States' (4,673), 'USA'
(712), 'US' (159), 'usa' (7), and 'United States of America' (2); the UK as
'United Kingdom' (505), 'UK' (22), 'united kingdom' (1). A handful of values
are not real countries at all ('Any Location': 7, 'European Union': 34) or
are typos ('Austalia': 2) — these map to None rather than a guessed code.
_ASHBY_ALIASES covers every distinct value seen in that census; an
unrecognized value returns None rather than guessing, same "honest null
beats a confident wrong answer" rule as pollers/seniority.py.
"""

_ASHBY_ALIASES: dict[str, str] = {
    "united states": "US", "usa": "US", "us": "US",
    "united states of america": "US",
    "united kingdom": "GB", "uk": "GB",
    "germany": "DE", "france": "FR", "france, metropolitan": "FR",
    "singapore": "SG", "canada": "CA", "south korea": "KR",
    "india": "IN", "australia": "AU", "netherlands": "NL",
    "switzerland": "CH", "china": "CN", "japan": "JP", "sweden": "SE",
    "philippines": "PH", "ireland": "IE", "united arab emirates": "AE",
    "italy": "IT", "brazil": "BR", "spain": "ES", "morocco": "MA",
    "mexico": "MX", "portugal": "PT", "poland": "PL", "israel": "IL",
    "south africa": "ZA", "belgium": "BE", "hong kong": "HK",
    "taiwan": "TW", "argentina": "AR", "serbia": "RS", "malaysia": "MY",
    "new zealand": "NZ", "vietnam": "VN", "ghana": "GH", "egypt": "EG",
    "slovakia": "SK", "colombia": "CO", "turkey": "TR", "nigeria": "NG",
    "kenya": "KE", "saudi arabia": "SA", "kuwait": "KW",
    "el salvador": "SV", "bangladesh": "BD", "hungary": "HU",
    "ukraine": "UA", "guatemala": "GT", "lithuania": "LT", "uganda": "UG",
    "norway": "NO", "indonesia": "ID", "costa rica": "CR", "finland": "FI",
    "romania": "RO", "qatar": "QA", "czechia": "CZ", "peru": "PE",
    "iceland": "IS", "croatia": "HR", "venezuela": "VE", "panama": "PA",
    "estonia": "EE", "denmark": "DK", "bulgaria": "BG", "gibraltar": "GI",
}


def normalize_smartrecruiters_country(raw: str | None) -> str | None:
    """SmartRecruiters already returns a clean lowercase ISO-2 code."""
    if not raw or not raw.strip():
        return None
    return raw.strip().upper()


def normalize_lever_country(raw: str | None) -> str | None:
    """Lever already returns a clean ISO-2 code."""
    if not raw or not raw.strip():
        return None
    return raw.strip().upper()


def normalize_ashby_country(raw: str | None) -> str | None:
    """Map Ashby's free-text country name to ISO-2, or None if unrecognized."""
    if not raw or not raw.strip():
        return None
    return _ASHBY_ALIASES.get(raw.strip().lower())
