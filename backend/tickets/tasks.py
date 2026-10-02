from celery import shared_task
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError
from celery import current_app
from datetime import timedelta
import logging

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
from .models import AILog, Ticket, TicketMessage, ResolutionNotification

logger = logging.getLogger(__name__)


def enqueue_resolution_notification(notification_id: int) -> None:
    """Submit work without allowing broker errors to turn a committed ticket update into a 500."""
    try:
        send_resolution_notification_task.delay(notification_id)
    except Exception as exc:
        logger.warning("Resolution notification enqueue failed (notification_id=%s, error_type=%s)", notification_id, type(exc).__name__)
        ResolutionNotification.objects.filter(pk=notification_id, delivery_status="pending").update(
            delivery_status="failed", error_detail="queue_unavailable", next_attempt_at=None
        )


@shared_task(bind=True, max_retries=2)
def send_resolution_notification_task(self, notification_id: int) -> str:
    """Send a tracked notification with a bounded, sanitized retry policy."""
    try:
        with transaction.atomic():
            notification = ResolutionNotification.objects.select_for_update().get(pk=notification_id)
            if notification.delivery_status in ("sent", "sending"):
                return notification.delivery_status
            if notification.attempt_count >= ResolutionNotification.MAX_ATTEMPTS:
                notification.delivery_status = "failed"
                notification.error_detail = "retry_limit_reached"
                notification.save(update_fields=["delivery_status", "error_detail"])
                return "failed"
            notification.delivery_status = "sending"
            notification.attempt_count += 1
            notification.last_attempt_at = timezone.now()
            notification.next_attempt_at = None
            notification.error_detail = ""
            notification.save(update_fields=["delivery_status", "attempt_count", "last_attempt_at", "next_attempt_at", "error_detail"])
        from .services.outbound_email import send_resolution_notification
        send_resolution_notification(notification)
        notification.delivery_status = "sent"
        notification.sent_at = timezone.now()
        notification.error_detail = ""
        notification.save(update_fields=["delivery_status", "sent_at", "error_detail"])
        return "sent"
    except Exception as exc:
        # Store exception classes only. SMTP exception text may contain addresses or server details.
        permanent_error = isinstance(exc, (ValueError, ValidationError))
        safe_error = "invalid_address" if permanent_error else "smtp_delivery_failed"
        logger.warning("Resolution notification delivery failed (notification_id=%s, error_type=%s)", notification_id, type(exc).__name__)
        notification = ResolutionNotification.objects.filter(pk=notification_id).first()
        if not notification:
            raise
        # In local eager mode a Celery retry executes inside the request callback;
        # record failure for a user initiated retry instead of bubbling SMTP errors
        # back after the ticket transaction has already committed.
        if permanent_error or notification.attempt_count >= ResolutionNotification.MAX_ATTEMPTS or current_app.conf.task_always_eager:
            notification.delivery_status = "failed"
            notification.next_attempt_at = None
            notification.error_detail = safe_error
            notification.save(update_fields=["delivery_status", "next_attempt_at", "error_detail"])
            return "failed"
        delay = 60 * (2 ** (notification.attempt_count - 1))
        notification.delivery_status = "pending"
        notification.next_attempt_at = timezone.now() + timedelta(seconds=delay)
        notification.error_detail = safe_error
        notification.save(update_fields=["delivery_status", "next_attempt_at", "error_detail"])
        raise self.retry(exc=exc, countdown=delay)


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
