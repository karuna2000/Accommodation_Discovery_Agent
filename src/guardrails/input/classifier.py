import re

HTML_TAG_RE = re.compile(r"<[^>]*>")
DANGEROUS_URI_RE = re.compile(r"(?:javascript|data|vbscript|livescript)\s*:", re.IGNORECASE)
PROHIBITED_TERMS_RE = re.compile(
    r"\b(bomb|explosive|weapon|drugs|illegal|hack|crack)\b", re.IGNORECASE
)


def sanitize(text: str) -> str:
    """Strip HTML tags from input text."""
    return HTML_TAG_RE.sub("", text)


def has_blocked_content(text: str) -> tuple[bool, str]:
    if DANGEROUS_URI_RE.search(text):
        return True, "Query contains blocked URI scheme"
    if PROHIBITED_TERMS_RE.search(text):
        return True, "Query contains prohibited terms"
    return False, ""


def validate_input(text: str) -> tuple[str | None, str | None]:
    """Returns (sanitized_query, reason) — query is None if blocked."""
    if not text or not text.strip():
        return None, "Query is empty"
    if len(text) > 500:
        return None, "Query too long"

    cleaned = sanitize(text)

    blocked, reason = has_blocked_content(cleaned)
    if blocked:
        return None, reason

    return cleaned, None
