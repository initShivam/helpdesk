from celery import shared_task
from django.conf import settings
from django.utils import timezone

from knowledge_base.retrieval import retrieve

from .ai_service import AISuggestionError, build_prompt, generate_with_gemini
from .models import AILog, Ticket, TicketMessage


@shared_task(bind=True, autoretry_for=(AISuggestionError,), retry_backoff=True, max_retries=2)
def generate_ai_suggestion(self, ticket_id: int) -> int:
    ticket = Ticket.objects.get(pk=ticket_id)
    log = AILog.objects.create(
        ticket=ticket,
        model=getattr(settings, "GEMINI_MODEL", "gemini-2.0-flash"),
        operation="suggest_reply",
        sanitized_prompt="",
    )
    try:
        messages = list(ticket.messages.order_by("created_at"))
        context = retrieve(f"{ticket.subject} {' '.join(message.body for message in messages)}")
        prompt = build_prompt(ticket, messages, context)
        log.sanitized_prompt = prompt
        log.retrieved_document_ids = [item.document_id for item in context]
        suggestion, usage = generate_with_gemini(prompt)
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
    except (AISuggestionError, RuntimeError, Ticket.DoesNotExist) as exc:
        log.status = "failed"
        log.error_message = str(exc)
        log.completed_at = timezone.now()
        log.save(update_fields=["status", "error_message", "completed_at", "sanitized_prompt"])
        raise
