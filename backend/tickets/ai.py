"""Ticket classification and summary generation."""

from dataclasses import dataclass
import logging
import re

from .models import Ticket

logger = logging.getLogger(__name__)


class AIAnalysisError(Exception):
    """Raised when ticket analysis cannot produce a valid result."""


@dataclass(frozen=True)
class TicketAnalysis:
    category: str
    priority: str
    summary: str
    confidence: float


_CATEGORY_KEYWORDS = {
    "technical": {
        "error",
        "broken",
        "crash",
        "failed",
        "failure",
        "install",
        "login",
        "password",
        "printer",
        "server",
        "software",
        "technical",
        "unable",
        " not working",
    },
    "refund": {
        "charge",
        "charged",
        "credit",
        "money back",
        "refund",
        "return",
        "billing",
        "payment",
        "invoice",
        "cancel",
    },
    "general": {
        "question",
        "how",
        "information",
        "hours",
        "pricing",
        "hello",
        "general",
    },
}

_HIGH_PRIORITY_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\burgent(?:ly)?\b",
        r"\bemergency\b",
        r"\bcritical(?:ly)?\b",
        r"\bimmediate(?:ly)?\b",
        r"\basap\b",
        r"\bsystem\s+down\b",
        r"\boutage\b",
        r"\b(?:cannot|can't|unable to)\s+access\b",
        r"\bdeadline\s+today\b",
        r"\bexam\s+today\b",
    )
)
_LOW_PRIORITY_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bwhen possible\b",
        r"\bwhen convenient\b",
        r"\bat your convenience\b",
        r"\bnot\s+(?:urgent|an emergency|critical)\b",
        r"\bno rush\b",
        r"\bnon[- ]urgent\b",
        r"\bnot time[- ]sensitive\b",
        r"\blow priority\b",
        r"\bgeneral question\b",
        r"\bsuggestion\b",
        r"\bfeedback\b",
        r"\binformation\b",
    )
)
_NEGATION_BEFORE_SIGNAL = re.compile(
    r"\b(?:not(?!\s+only)|no|never|without|non|isn't|aren't|wasn't|weren't|doesn't|don't|didn't)"
    r"(?:\W+\w+){0,2}\W*$",
    re.IGNORECASE,
)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _keyword_matches(text: str, keyword: str) -> bool:
    if keyword.startswith(" "):
        return keyword in text
    return re.search(rf"\b{re.escape(keyword)}\b", text) is not None


def _classify(text: str) -> tuple[str, float]:
    scores = {
        category: sum(_keyword_matches(text, keyword) for keyword in keywords)
        for category, keywords in _CATEGORY_KEYWORDS.items()
    }
    category, score = max(scores.items(), key=lambda item: item[1])
    if score == 0:
        return "general", 0.5

    runner_up = max(
        value for key, value in scores.items() if key != category
    )
    confidence = min(0.99, 0.65 + (score - runner_up) * 0.1)
    return category, round(confidence, 2)


def _summary(subject: str, body: str) -> str:
    source = _normalise(body) or _normalise(subject)
    if not source:
        return ""
    first_sentence = re.split(r"(?<=[.!?])\s+", source, maxsplit=1)[0]
    return first_sentence[:240].rstrip()


def _has_unnegated_high_priority_signal(text: str) -> bool:
    for pattern in _HIGH_PRIORITY_PATTERNS:
        for match in pattern.finditer(text):
            prefix = text[max(0, match.start() - 50):match.start()]
            if _NEGATION_BEFORE_SIGNAL.search(prefix):
                continue
            return True
    return False


def _priority(text: str) -> str:
    if _has_unnegated_high_priority_signal(text):
        return "high"
    if any(pattern.search(text) for pattern in _LOW_PRIORITY_PATTERNS):
        return "low"
    return "medium"


def analyze_ticket(subject: str, body: str = "") -> TicketAnalysis:
    """Analyze ticket text using deterministic local heuristics."""

    normalized_subject = _normalise(subject)
    normalized_body = _normalise(body)
    text = f"{normalized_subject} {normalized_body}".lower()
    category, confidence = _classify(text)
    return TicketAnalysis(
        category=category,
        priority=_priority(text),
        summary=_summary(normalized_subject, normalized_body),
        confidence=confidence,
    )


def enrich_ticket(ticket: Ticket, body: str = "") -> bool:
    """Save analysis results on a ticket, returning False for expected failures."""

    try:
        analysis = analyze_ticket(ticket.subject, body)
    except (AIAnalysisError, AttributeError, RuntimeError, TypeError, ValueError) as exc:
        logger.exception("Ticket AI analysis failed for ticket %s: %s", ticket.pk, exc)
        return False

    ticket.category = analysis.category
    ticket.priority = analysis.priority
    ticket.ai_summary = analysis.summary
    ticket.ai_category_confidence = analysis.confidence
    ticket.save(
        update_fields=[
            "category",
            "priority",
            "ai_summary",
            "ai_category_confidence",
            "updated_at",
        ]
    )
    return True
