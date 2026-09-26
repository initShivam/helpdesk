import json
import re
from urllib import error, request

from django.conf import settings

from knowledge_base.retrieval import RetrievedChunk


class AISuggestionError(Exception):
    """Raised when a suggested reply cannot be generated."""


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


def build_prompt(ticket, messages: list, context: list[RetrievedChunk]) -> str:
    conversation = "\n".join(
        f"{message.message_type}: {message.body}" for message in messages
    )
    references = "\n\n".join(
        f"Reference: {item.title}\n{item.content}" for item in context
    ) or "No knowledge-base reference matched this ticket."
    return sanitize_prompt(
        "You are a professional helpdesk agent. Draft a concise, empathetic reply "
        "that directly addresses the customer. Do not invent policy. If the "
        "references do not answer the question, say the issue will be reviewed.\n\n"
        f"Ticket subject: {ticket.subject}\nConversation:\n{conversation}\n\n"
        f"Knowledge base:\n{references}"
    )


def generate_with_gemini(prompt: str) -> tuple[str, dict]:
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise AISuggestionError("GEMINI_API_KEY is not configured.")

    model = getattr(settings, "GEMINI_MODEL", "gemini-2.0-flash")
    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        f"?key={api_key}"
    )
    payload = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 500},
        }
    ).encode("utf-8")
    req = request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=getattr(settings, "AI_SUGGESTION_TIMEOUT", 30)) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        raise AISuggestionError("Gemini request failed.") from exc

    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise AISuggestionError("Gemini returned no usable suggestion.") from exc
    if not text:
        raise AISuggestionError("Gemini returned an empty suggestion.")
    return text, data.get("usageMetadata", {})
