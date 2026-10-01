import re


_PII_PATTERNS = (
    (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I), "[email redacted]"),
    (re.compile(r"\b(?:\+?\d[\d\s().-]{7,}\d)\b"), "[phone redacted]"),
)
_PROFANITY = re.compile(r"\b(?:fuck|shit|bitch|asshole)\b", re.I)


def sanitize_prompt(value: str) -> str:
    sanitized = value
    for pattern, replacement in _PII_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return _PROFANITY.sub("[language removed]", sanitized)
