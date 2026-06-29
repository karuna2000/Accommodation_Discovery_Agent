import re

BLOCKED_PATTERNS = [
    re.compile(r"<script", re.IGNORECASE),
    re.compile(r"javascript:"),
    re.compile(r"on\w+\s*="),
]

ACCOMMODATION_KEYWORDS = [
    "rent", "apartment", "studio", "condo", "house", "room",
    "bedroom", "bathroom", "lease", "property", "listing",
    "accommodation", "housing", "flat", "dorm", "suite",
    "near", "price", "monthly", "utilities", "furnished",
    "landlord", "sublet", "utilities included",
]


def classify_intent(query: str) -> tuple[bool, str | None]:
    if len(query.strip()) < 3:
        return False, "Query too short"

    words = query.lower().split()
    keyword_matches = sum(1 for kw in ACCOMMODATION_KEYWORDS if kw in words or kw in query.lower())

    if keyword_matches == 0:
        return False, "Query not related to accommodation search"

    return True, None


def filter_content(query: str) -> tuple[bool, str | None]:
    for pattern in BLOCKED_PATTERNS:
        if pattern.search(query):
            return False, "Query contains blocked content patterns"

    toxic_patterns = [
        r"\b(bomb|explosive|weapon|drugs|illegal|hack|crack)\b",
    ]
    for pat in toxic_patterns:
        if re.search(pat, query, re.IGNORECASE):
            return False, "Query contains prohibited terms"

    return True, None


def validate_input(query: str) -> str | None:
    ok, reason = classify_intent(query)
    if not ok:
        return reason
    ok, reason = filter_content(query)
    if not ok:
        return reason
    return None
