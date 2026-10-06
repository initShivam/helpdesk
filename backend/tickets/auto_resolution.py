"""Similarity retrieval and safety checks for automatic ticket responses."""

from dataclasses import dataclass
import json
import math
import re

from django.conf import settings

from helpdesk.ai_privacy import sanitize_prompt
from knowledge_base.embeddings import cosine_similarity, embed_text
from .ai_service import build_auto_resolution_prompt, generate_with_openai
from .models import ResolvedTicketKnowledge, Ticket, TicketMessage


@dataclass(frozen=True)
class ResolutionMatch:
    ticket_id: int
    problem: str
    resolution: str
    score: float


@dataclass(frozen=True)
class GeneratedResolution:
    response: str
    confidence: float
    needs_review: bool
    prompt: str


_RISK_PATTERNS = (
    re.compile(r"\brefund(?:s|ed|ing)?\b", re.IGNORECASE),
    re.compile(r"\b(?:billing|charged|chargeback|credit card|payment dispute)\b", re.IGNORECASE),
    re.compile(r"\b(?:legal|attorney|lawyer|lawsuit|police|fraud)\b", re.IGNORECASE),
    re.compile(r"\b(?:hacked|data breach|data leak|account takeover|security incident)\b", re.IGNORECASE),
    re.compile(r"\b(?:urgent|emergency|immediately|asap|system down|outage)\b", re.IGNORECASE),
)
_UNSUPPORTED_ACTION_PATTERNS = (
    re.compile(
        r"\b(?:i|we|our team)\s+(?:have|has|already|will|are going to)\s+"
        r"(?:refund\w*|credit\w*|reimburse\w*|waive\w*|cancel\w*|delete\w*|"
        r"reset\w*|change\w*|update\w*|fix\w*|restore\w*|process\w*|"
        r"submit\w*|escalate\w*|approve\w*)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:guarantee|guaranteed|promise|promised|will definitely|"
        r"you will receive|will be resolved|within \d+ days)\b",
        re.IGNORECASE,
    ),
)
_GENERIC_RESOLUTION_PATTERN = re.compile(
    r"^(?:thanks|thank you|you are welcome|you're welcome|noted|okay|ok|done)[.! ]*$",
    re.IGNORECASE,
)


def _problem_text(ticket: Ticket) -> str:
    return sanitize_prompt(
        f"Subject: {ticket.subject}\nCustomer issue: {ticket.description or ticket.subject}"
    )


def _is_meaningful_resolution(body: str) -> bool:
    text = body.strip()
    return (
        len(text) >= 40
        and len(text.split()) >= 6
        and not _GENERIC_RESOLUTION_PATTERN.fullmatch(text)
    )


def find_similar_resolutions(ticket: Ticket) -> list[ResolutionMatch]:
    """Return relevant prior resolved tickets with human-authored agent replies."""
    candidates = (
        Ticket.objects.filter(
            status="resolved",
            messages__message_type="agent",
            messages__is_ai_generated=False,
            messages__is_draft=False,
        )
        .exclude(pk=ticket.pk)
        .distinct()
        .order_by("-updated_at")[: max(1, settings.AI_AUTO_RESOLUTION_CANDIDATE_LIMIT)]
    )
    current_embedding, current_model = embed_text(_problem_text(ticket))
    matches: list[ResolutionMatch] = []

    for historical in candidates:
        resolution_messages = (
            TicketMessage.objects.filter(
                ticket=historical,
                message_type="agent",
                is_ai_generated=False,
                is_draft=False,
            )
            .order_by("-created_at")
        )
        resolution_message = next(
            (
                message
                for message in resolution_messages
                if _is_meaningful_resolution(message.body)
            ),
            None,
        )
        if not resolution_message or not resolution_message.body.strip():
            continue

        problem = _problem_text(historical)
        resolution = sanitize_prompt(resolution_message.body)
        knowledge, _ = ResolvedTicketKnowledge.objects.get_or_create(ticket=historical)
        if (
            knowledge.problem_text != problem
            or knowledge.resolution_text != resolution
            or knowledge.embedding_model != current_model
            or len(knowledge.embedding) != len(current_embedding)
        ):
            vector, model = embed_text(problem)
            knowledge.problem_text = problem
            knowledge.resolution_text = resolution
            knowledge.embedding = vector
            knowledge.embedding_model = model
            knowledge.save(
                update_fields=[
                    "problem_text",
                    "resolution_text",
                    "embedding",
                    "embedding_model",
                    "updated_at",
                ]
            )

        if knowledge.embedding_model != current_model:
            continue
        score = cosine_similarity(current_embedding, knowledge.embedding)
        if score >= settings.AI_AUTO_RESOLUTION_RETRIEVAL_MIN_SIMILARITY:
            matches.append(
                ResolutionMatch(
                    ticket_id=historical.pk,
                    problem=knowledge.problem_text,
                    resolution=knowledge.resolution_text,
                    score=round(max(-1.0, min(1.0, score)), 4),
                )
            )

    return sorted(matches, key=lambda match: match.score, reverse=True)[
        : max(1, settings.AI_AUTO_RESOLUTION_MAX_MATCHES)
    ]


def ticket_requires_manual_review(ticket: Ticket) -> str:
    if ticket.ai_category_confidence is None or ticket.ai_category_confidence < 0.65:
        return "classification_uncertain"
    if ticket.category == "refund":
        return "sensitive_category"
    if ticket.priority in {"high", "urgent"}:
        return "high_priority"
    content = f"{ticket.subject}\n{ticket.description}".strip()
    if any(pattern.search(content) for pattern in _RISK_PATTERNS):
        return "sensitive_or_urgent_content"
    return ""


def generate_resolution(ticket: Ticket, matches: list[ResolutionMatch]) -> GeneratedResolution:
    customer_message = (
        ticket.messages.filter(message_type="customer").order_by("-created_at").first()
    )
    prompt = build_auto_resolution_prompt(
        ticket,
        sanitize_prompt(customer_message.body if customer_message else ticket.description),
        matches,
    )
    output, _ = generate_with_openai(prompt)
    try:
        data = json.loads(output)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid_response_format") from exc

    reply = data.get("response")
    confidence = data.get("confidence")
    needs_review = data.get("needs_review")
    if (
        not isinstance(reply, str)
        or not reply.strip()
        or len(reply) > 4000
        or not isinstance(confidence, (int, float))
        or isinstance(confidence, bool)
        or not math.isfinite(confidence)
        or not 0 <= confidence <= 1
        or not isinstance(needs_review, bool)
    ):
        raise ValueError("invalid_response_fields")

    return GeneratedResolution(
        response=reply.strip(),
        confidence=float(confidence),
        needs_review=needs_review,
        prompt=prompt,
    )


def response_requires_manual_review(response_text: str) -> bool:
    return any(pattern.search(response_text) for pattern in _UNSUPPORTED_ACTION_PATTERNS)
