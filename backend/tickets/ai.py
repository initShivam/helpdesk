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


def analyze_ticket(subject: str, body: str = "") -> TicketAnalysis:
    """Analyze ticket text using deterministic local heuristics."""

    normalized_subject = _normalise(subject)
    normalized_body = _normalise(body)
    text = f"{normalized_subject} {normalized_body}".lower()
    category, confidence = _classify(text)
    return TicketAnalysis(
        category=category,
        summary=_summary(normalized_subject, normalized_body),
        confidence=confidence,
    )


def enrich_ticket(ticket: Ticket, body: str = "") -> bool:
    """Save analysis results on a ticket, returning False for expected failures."""

    try:
        analysis = analyze_ticket(ticket.subject, body)
    except Exception as exc:
        logger.exception("Ticket AI analysis failed for ticket %s: %s", ticket.pk, exc)
        return False

    ticket.category = analysis.category
    ticket.ai_summary = analysis.summary
    ticket.ai_category_confidence = analysis.confidence
    ticket.save(
        update_fields=[
            "category",
            "ai_summary",
            "ai_category_confidence",
            "updated_at",
        ]
    )
    return True
