import re

PII_PATTERNS = [
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "<EMAIL>"),
    (re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"), "<PHONE>"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "<SSN>"),
    (re.compile(r"\b(?:\d[ -]*?){13,16}\b"), "<CC_NUMBER>"),
]


def strip_pii(text: str) -> str:
    result = text
    for pattern, replacement in PII_PATTERNS:
        result = pattern.sub(replacement, result)
    return result
