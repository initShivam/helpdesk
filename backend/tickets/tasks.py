from celery import shared_task
from django.conf import settings
from django.utils import timezone

from knowledge_base.retrieval import retrieve
from knowledge_base.embeddings import EmbeddingError

from .ai_service import (
    AISuggestionError,
    build_classification_prompt,
    build_prompt,
    build_summary_prompt,
    generate_with_openai,
    parse_classification_response,
)
from .models import AILog, Ticket, TicketMessage


@shared_task
def generate_ai_suggestion(ticket_id: int) -> int:
    ticket = Ticket.objects.get(pk=ticket_id)
    log = AILog.objects.create(
        ticket=ticket,
        model=getattr(settings, "OPENAI_MODEL", "gpt-6-luna"),
        operation="suggest_reply",
        sanitized_prompt="",
    )
    try:
        messages = list(ticket.messages.order_by("created_at"))
        context = retrieve(f"{ticket.subject} {' '.join(message.body for message in messages)}")
        prompt = build_prompt(ticket, messages, context)
        log.sanitized_prompt = prompt
        log.retrieved_document_ids = [item.document_id for item in context]
        suggestion, usage = generate_with_openai(prompt)
        log.status = "succeeded"
        log.response_text = suggestion
        log.token_usage = usage
        log.completed_at = timezone.now()
        log.save(
            update_fields=[
                "sanitized_prompt",
                "retrieved_document_ids",
                "status",
                "response_text",
                "token_usage",
                "completed_at",
            ]
        )
        TicketMessage.objects.create(
            ticket=ticket,
            body=suggestion,
            message_type="agent",
            is_ai_generated=True,
            is_draft=True,
            ai_log=log,
        )
        return log.id
    except (AISuggestionError, EmbeddingError, RuntimeError, Ticket.DoesNotExist) as exc:
        log.status = "failed"
        log.error_message = str(exc)
        log.completed_at = timezone.now()
        log.save(update_fields=["status", "error_message", "completed_at", "sanitized_prompt"])
        raise


@shared_task
def classify_ticket(ticket_id: int) -> str:
    """Classify a ticket using OpenAI with few-shot examples and persist the predicted category."""
    ticket = Ticket.objects.get(pk=ticket_id)
    log = AILog.objects.create(
        ticket=ticket,
        model=getattr(settings, "OPENAI_MODEL", "gpt-6-luna"),
        operation="classify",
        sanitized_prompt="",
    )
    try:
        messages = list(ticket.messages.order_by("created_at"))
        prompt = build_classification_prompt(ticket, messages)
        log.sanitized_prompt = prompt
        response_text, usage = generate_with_openai(prompt)
        predicted_category = parse_classification_response(response_text)
        log.status = "succeeded"
        log.response_text = predicted_category
        log.token_usage = usage
        log.completed_at = timezone.now()
        log.save(
            update_fields=[
                "sanitized_prompt",
                "status",
                "response_text",
                "token_usage",
                "completed_at",
            ]
        )
        ticket.category = predicted_category
        ticket.ai_category_confidence = 0.95
        ticket.save(update_fields=["category", "ai_category_confidence", "updated_at"])
        return predicted_category
    except (AISuggestionError, RuntimeError, Ticket.DoesNotExist) as exc:
        log.status = "failed"
        log.error_message = str(exc)
        log.completed_at = timezone.now()
        log.save(update_fields=["status", "error_message", "completed_at", "sanitized_prompt"])
        raise


@shared_task
def summarize_ticket(ticket_id: int) -> str:
    """Create a concise AI-generated summary message for a ticket."""
    ticket = Ticket.objects.get(pk=ticket_id)
    log = AILog.objects.create(
        ticket=ticket,
        model=getattr(settings, "OPENAI_MODEL", "gpt-6-luna"),
        operation="summarize",
        sanitized_prompt="",
    )
    try:
        messages = list(ticket.messages.order_by("created_at"))
        prompt = build_summary_prompt(ticket, messages)
        log.sanitized_prompt = prompt
        summary_text, usage = generate_with_openai(prompt)
        log.status = "succeeded"
        log.response_text = summary_text
        log.token_usage = usage
        log.completed_at = timezone.now()
        log.save(
            update_fields=[
                "sanitized_prompt",
                "status",
                "response_text",
                "token_usage",
                "completed_at",
            ]
        )
        ticket.ai_summary = summary_text
        ticket.save(update_fields=["ai_summary", "updated_at"])
        TicketMessage.objects.create(
            ticket=ticket,
            body=summary_text,
            message_type="system",
            is_ai_generated=True,
            is_draft=False,
            ai_log=log,
        )
        return summary_text
    except (AISuggestionError, RuntimeError, Ticket.DoesNotExist) as exc:
        log.status = "failed"
        log.error_message = str(exc)
        log.completed_at = timezone.now()
        log.save(update_fields=["status", "error_message", "completed_at", "sanitized_prompt"])
        raise
