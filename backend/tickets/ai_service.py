import json
import re
from urllib import error, request

from django.conf import settings
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from knowledge_base.retrieval import RetrievedChunk


class AISuggestionError(Exception):
    """Raised when a suggested reply cannot be generated."""


class AIConfigurationError(AISuggestionError):
    """Raised for AI setup problems that retries cannot resolve."""


class AIRetryableError(AISuggestionError):
    """Raised for transient provider failures that can succeed on retry."""


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
        raise AIConfigurationError("GEMINI_API_KEY is not configured. Add it to the root .env file and restart Django.")
    return _generate_with_gemini(prompt, api_key)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(AIRetryableError),
    reraise=True,
)
def _generate_with_gemini(prompt: str, api_key: str) -> tuple[str, dict]:
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
    except error.HTTPError as exc:
        if exc.code == 429 or exc.code >= 500:
            raise AIRetryableError(f"Gemini temporarily unavailable (HTTP {exc.code}).") from exc
        raise AIConfigurationError(
            f"Gemini rejected the request (HTTP {exc.code}); check the API key, model, and quota."
        ) from exc
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise AIRetryableError("Gemini request failed temporarily.") from exc

    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise AISuggestionError("Gemini returned no usable suggestion.") from exc
    if not text:
        raise AISuggestionError("Gemini returned an empty suggestion.")
    return text, data.get("usageMetadata", {})


def build_classification_prompt(ticket, messages: list | None = None) -> str:
    """Build a few-shot prompt to classify a ticket into general, technical, or refund."""
    conversation_body = ""
    if messages:
        conversation_body = "\n".join(f"{m.message_type}: {m.body}" for m in messages)
    description = ticket.description or ""
    ticket_content = f"Ticket Subject: {ticket.subject}\nTicket Description: {description}"
    if conversation_body:
        ticket_content += f"\nConversation History:\n{conversation_body}"

    prompt = (
        "You are an expert customer support ticket classifier.\n"
        "Classify the customer support ticket into exactly ONE of the following categories:\n"
        "- general\n"
        "- technical\n"
        "- refund\n\n"
        "Category guidelines:\n"
        "- general: General inquiries, greetings, product questions, business hours, account policies, feedback.\n"
        "- technical: Technical problems, software errors, login failures, broken features, crashes, outages, bugs.\n"
        "- refund: Payment issues, billing discrepancies, refund requests, unwanted charges, cancellation refunds.\n\n"
        "Few-shot examples:\n\n"
        "Ticket Subject: Office hours inquiry\n"
        "Ticket Description: When are you open on Sundays and what is the address?\n"
        "Category: general\n\n"
        "Ticket Subject: Server connection error 502\n"
        "Ticket Description: The dashboard is throwing a 502 Bad Gateway whenever I log in.\n"
        "Category: technical\n\n"
        "Ticket Subject: Cancel plan and request money back\n"
        "Ticket Description: I was charged accidentally for an annual subscription and need a refund.\n"
        "Category: refund\n\n"
        "Now classify the following ticket:\n"
        f"{ticket_content}\n\n"
        "Respond with ONLY the category name: general, technical, or refund."
    )
    return sanitize_prompt(prompt)


def parse_classification_response(raw_text: str) -> str:
    """Parse Gemini's raw output and normalize to a valid category choice."""
    text = raw_text.strip().lower()
    for cat in ("technical", "refund", "general"):
        if cat in text:
            return cat
    return "general"


def build_summary_prompt(ticket, messages: list | None = None) -> str:
    """Build a prompt to generate a concise summary of the ticket and conversation."""
    conversation_body = ""
    if messages:
        conversation_body = "\n".join(f"{m.message_type}: {m.body}" for m in messages)
    description = ticket.description or ""
    ticket_content = f"Ticket Subject: {ticket.subject}\nTicket Description: {description}"
    if conversation_body:
        ticket_content += f"\nConversation History:\n{conversation_body}"

    prompt = (
        "You are a professional customer support assistant. Provide a concise, clear summary "
        "of the following customer support ticket and its conversation in 1 to 2 sentences. "
        "Highlight the customer's core issue and the current situation.\n\n"
        f"{ticket_content}\n\n"
        "Summary:"
    )
    return sanitize_prompt(prompt)
