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
from .models import (
    AILog,
    AutoResolutionAudit,
    CustomerContact,
    Ticket,
    TicketMessage,
    ResolutionNotification,
    WhatsAppNotification,
    get_auto_resolution_settings,
)

logger = logging.getLogger(__name__)


def enqueue_auto_resolution(ticket_id: int) -> None:
    if not get_auto_resolution_settings().enabled:
        return
    try:
        process_auto_resolution.delay(ticket_id)
    except Exception as exc:
        logger.warning(
            "Auto-resolution enqueue failed (ticket_id=%s, error_type=%s)",
            ticket_id,
            type(exc).__name__,
        )
        AutoResolutionAudit.objects.update_or_create(
            ticket_id=ticket_id,
            defaults={
                "decision": "agent_review",
                "decision_reason": "queue_unavailable",
                "send_status": "not_sent",
            },
        )


@shared_task
def process_auto_resolution(ticket_id: int) -> int:
    from .auto_resolution import (
        find_similar_resolutions,
        generate_resolution,
        response_requires_manual_review,
        ticket_requires_manual_review,
    )
    ticket = Ticket.objects.get(pk=ticket_id)
    config = get_auto_resolution_settings()
    if not config.enabled:
        return ticket.pk

    channel = ticket.source.lower()
    if channel not in {"email", "whatsapp"}:
        channel = ""
    audit, created = AutoResolutionAudit.objects.get_or_create(
        ticket=ticket,
        defaults={"channel": channel, "decision": "processing"},
    )
    if not created:
        return audit.pk

    if not channel:
        audit.decision = "agent_review"
        audit.decision_reason = "unsupported_delivery_channel"
        audit.save(update_fields=["decision", "decision_reason", "updated_at"])
        return audit.pk

    channel_enabled = (
        config.email_auto_reply if channel == "email" else config.whatsapp_auto_reply
    )
    if not channel_enabled:
        audit.decision = "agent_review"
        audit.decision_reason = f"{channel}_auto_reply_disabled"
        audit.save(update_fields=["decision", "decision_reason", "updated_at"])
        return audit.pk

    review_reason = ticket_requires_manual_review(ticket)
    if review_reason:
        audit.decision = "agent_review"
        audit.decision_reason = review_reason
        audit.save(update_fields=["decision", "decision_reason", "updated_at"])
        return audit.pk

    try:
        matches = find_similar_resolutions(ticket)
    except EmbeddingError as exc:
        logger.warning(
            "Auto-resolution retrieval failed (ticket_id=%s, error_type=%s)",
            ticket_id,
            type(exc).__name__,
        )
        audit.decision = "agent_review"
        audit.decision_reason = "retrieval_unavailable"
        audit.save(update_fields=["decision", "decision_reason", "updated_at"])
        return audit.pk

    audit.matched_ticket_ids = [match.ticket_id for match in matches]
    audit.matched_similarities = [
        {"ticket_id": match.ticket_id, "score": match.score} for match in matches
    ]
    audit.similarity_score = matches[0].score if matches else None
    audit.selected_match_id = matches[0].ticket_id if matches else None
    config = get_auto_resolution_settings()
    channel_enabled = (
        config.email_auto_reply if channel == "email" else config.whatsapp_auto_reply
    )
    if not config.enabled or not channel_enabled:
        audit.decision = "agent_review"
        audit.decision_reason = "auto_resolution_disabled_during_retrieval"
        audit.save(
            update_fields=[
                "matched_ticket_ids",
                "matched_similarities",
                "selected_match_id",
                "similarity_score",
                "decision",
                "decision_reason",
                "updated_at",
            ]
        )
        return audit.pk
    if not matches:
        audit.decision = "agent_review"
        audit.decision_reason = "no_similar_resolved_case"
        audit.save(
            update_fields=[
                "matched_ticket_ids",
                "matched_similarities",
                "selected_match_id",
                "similarity_score",
                "decision",
                "decision_reason",
                "updated_at",
            ]
        )
        return audit.pk

    log = AILog.objects.create(
        ticket=ticket,
        model=getattr(settings, "OPENAI_MODEL", "gpt-6-luna"),
        operation="auto_resolution",
        sanitized_prompt="",
    )
    audit.ai_log = log
    from .ai_service import AISuggestionError
    try:
        generated = generate_resolution(ticket, matches)
    except (AISuggestionError, ValueError, TypeError) as exc:
        logger.warning(
            "Auto-resolution generation failed (ticket_id=%s, error_type=%s)",
            ticket_id,
            type(exc).__name__,
        )
        log.status = "failed"
        log.error_message = type(exc).__name__
        log.completed_at = timezone.now()
        log.save(update_fields=["status", "error_message", "completed_at"])
        audit.decision = "agent_review"
        audit.decision_reason = "generation_failed"
        audit.save(
            update_fields=[
                "ai_log",
                "matched_ticket_ids",
                "matched_similarities",
                "selected_match_id",
                "similarity_score",
                "decision",
                "decision_reason",
                "updated_at",
            ]
        )
        return audit.pk

    log.sanitized_prompt = generated.prompt
    log.response_text = generated.response
    log.status = "succeeded"
    log.completed_at = timezone.now()
    log.save(
        update_fields=[
            "sanitized_prompt",
            "response_text",
            "status",
            "completed_at",
        ]
    )
    audit.generated_response = generated.response
    audit.ai_confidence = generated.confidence
    config = get_auto_resolution_settings()
    channel_enabled = (
        config.email_auto_reply if channel == "email" else config.whatsapp_auto_reply
    )

    TicketMessage.objects.create(
        ticket=ticket,
        body=generated.response,
        message_type="agent",
        is_ai_generated=True,
        is_draft=True,
        ai_log=log,
    )

    if not config.enabled or not channel_enabled:
        audit.decision = "agent_review"
        audit.decision_reason = "auto_resolution_disabled_during_generation"
    elif generated.needs_review:
        audit.decision = "agent_review"
        audit.decision_reason = "model_requested_review"
    elif response_requires_manual_review(generated.response):
        audit.decision = "agent_review"
        audit.decision_reason = "unsupported_action_or_promise"
    elif audit.similarity_score < config.minimum_threshold:
        audit.decision = "agent_review"
        audit.decision_reason = "similarity_below_threshold"
    elif generated.confidence < config.minimum_threshold:
        audit.decision = "agent_review"
        audit.decision_reason = "confidence_below_threshold"
    elif channel == "whatsapp" and settings.WHATSAPP_PROVIDER != "green_api":
        audit.decision = "agent_review"
        audit.decision_reason = "whatsapp_template_restricted"
        audit.send_status = "unavailable"
        audit.send_error = "generated_text_not_supported_by_template"
        audit.provider_result = "template_restricted"
    elif channel == "whatsapp" and not _has_whatsapp_consent(ticket):
        audit.decision = "agent_review"
        audit.decision_reason = "whatsapp_consent_required"
        audit.send_status = "unavailable"
        audit.send_error = "whatsapp_consent_required"
        audit.provider_result = "green_api"
    elif config.simulation_mode:
        audit.decision = "simulation"
        audit.decision_reason = "simulation_mode"
    else:
        audit.decision = "auto_send"
        audit.decision_reason = "confidence_and_safety_checks_passed"
        audit.send_status = "pending"
        if channel == "whatsapp":
            audit.provider_result = "green_api_pending"

    audit.save(
        update_fields=[
            "ai_log",
            "generated_response",
            "ai_confidence",
            "decision",
            "decision_reason",
            "send_status",
            "matched_ticket_ids",
            "matched_similarities",
            "similarity_score",
            "selected_match_id",
            "channel",
            "send_error",
            "provider_result",
            "updated_at",
        ]
    )
    if audit.decision == "auto_send":
        latest_config = get_auto_resolution_settings()
        latest_channel_enabled = (
            latest_config.email_auto_reply
            if channel == "email"
            else latest_config.whatsapp_auto_reply
        )
        if (
            not latest_config.enabled
            or not latest_channel_enabled
            or audit.similarity_score < latest_config.minimum_threshold
            or audit.ai_confidence < latest_config.minimum_threshold
        ):
            AutoResolutionAudit.objects.filter(pk=audit.pk).update(
                decision="agent_review",
                decision_reason="settings_or_threshold_changed_before_send",
                send_status="not_sent",
                updated_at=timezone.now(),
            )
            return audit.pk
        if latest_config.simulation_mode:
            AutoResolutionAudit.objects.filter(pk=audit.pk).update(
                decision="simulation",
                decision_reason="simulation_mode",
                send_status="not_sent",
                updated_at=timezone.now(),
            )
            return audit.pk
        try:
            if channel == "whatsapp":
                send_auto_resolution_whatsapp_task.delay(audit.pk)
            else:
                send_auto_resolution_email_task.delay(audit.pk)
        except Exception as exc:
            logger.warning(
                "Auto-resolution delivery enqueue failed (ticket_id=%s, error_type=%s)",
                ticket_id,
                type(exc).__name__,
            )
            AutoResolutionAudit.objects.filter(pk=audit.pk).update(
                decision="agent_review",
                decision_reason="delivery_queue_unavailable",
                send_status="failed",
                send_error="queue_unavailable",
                updated_at=timezone.now(),
            )
    return audit.pk


def _has_whatsapp_consent(ticket: Ticket) -> bool:
    contact = CustomerContact.objects.filter(
        email__iexact=ticket.requester_email
    ).first()
    return bool(
        contact
        and contact.whatsapp_consent
        and contact.whatsapp_number
    )


@shared_task
def send_auto_resolution_email_task(audit_id: int) -> str:
    from .models import AutoResolutionAudit
    from .services.outbound_email import send_customer_response

    with transaction.atomic():
        audit = AutoResolutionAudit.objects.select_for_update().select_related("ticket").get(pk=audit_id)
        if audit.send_status == "sending":
            audit.decision = "agent_review"
            audit.decision_reason = "delivery_outcome_unknown"
            audit.send_status = "failed"
            audit.send_error = "delivery_outcome_unknown"
            audit.provider_result = "delivery_outcome_unknown"
            audit.save(
                update_fields=[
                    "decision",
                    "decision_reason",
                    "send_status",
                    "send_error",
                    "provider_result",
                    "updated_at",
                ]
            )
            return audit.send_status
        if audit.send_status != "pending":
            return audit.send_status
        config = get_auto_resolution_settings()
        if (
            not config.enabled
            or audit.channel != "email"
            or not config.email_auto_reply
        ):
            audit.decision = "agent_review"
            audit.decision_reason = "auto_resolution_disabled_before_send"
            audit.send_status = "not_sent"
            audit.save(
                update_fields=["decision", "decision_reason", "send_status", "updated_at"]
            )
            return audit.send_status
        if (
            audit.similarity_score is None
            or audit.ai_confidence is None
            or audit.similarity_score < config.minimum_threshold
            or audit.ai_confidence < config.minimum_threshold
        ):
            audit.decision = "agent_review"
            audit.decision_reason = "settings_or_threshold_changed_before_send"
            audit.send_status = "not_sent"
            audit.save(
                update_fields=["decision", "decision_reason", "send_status", "updated_at"]
            )
            return audit.send_status
        if config.simulation_mode:
            audit.decision = "simulation"
            audit.decision_reason = "simulation_mode"
            audit.send_status = "not_sent"
            audit.save(
                update_fields=["decision", "decision_reason", "send_status", "updated_at"]
            )
            return audit.send_status
        if audit.ticket.status != "open":
            audit.decision = "agent_review"
            audit.decision_reason = "ticket_no_longer_open"
            audit.send_status = "not_sent"
            audit.save(
                update_fields=[
                    "decision",
                    "decision_reason",
                    "send_status",
                    "updated_at",
                ]
            )
            return audit.send_status
        audit.send_status = "sending"
        audit.send_attempts += 1
        audit.provider_result = "email_backend_attempted"
        audit.save(update_fields=["send_status", "send_attempts", "updated_at"])

    try:
        send_customer_response(audit.ticket, audit.generated_response)
    except Exception as exc:
        logger.warning(
            "Auto-resolution email failed (audit_id=%s, error_type=%s)",
            audit_id,
            type(exc).__name__,
        )
        permanent_error = isinstance(exc, (ValueError, ValidationError))
        AutoResolutionAudit.objects.filter(pk=audit_id).update(
            decision="agent_review",
            decision_reason="email_delivery_failed",
            send_status="failed",
            send_error="invalid_address" if permanent_error else "email_delivery_failed",
            provider_result="delivery_outcome_unknown" if not permanent_error else "rejected_before_send",
            updated_at=timezone.now(),
        )
        return "failed"

    with transaction.atomic():
        audit = AutoResolutionAudit.objects.select_for_update().select_related("ticket").get(pk=audit_id)
        if audit.send_status != "sent":
            audit.send_status = "sent"
            audit.decision = "auto_sent"
            audit.send_error = ""
            audit.provider_result = "accepted_by_email_backend"
            audit.save(
                update_fields=[
                    "send_status",
                    "decision",
                    "send_error",
                    "provider_result",
                    "updated_at",
                ]
            )
            TicketMessage.objects.get_or_create(
                ticket=audit.ticket,
                ai_log=audit.ai_log,
                is_draft=False,
                defaults={
                    "body": audit.generated_response,
                    "message_type": "agent",
                    "is_ai_generated": True,
                },
            )
    return "sent"


@shared_task
def send_auto_resolution_whatsapp_task(audit_id: int) -> str:
    from .models import AutoResolutionAudit
    from .services.whatsapp_service import configuration_ready
    from whatsapp.services import get_state_instance, send_whatsapp_message

    with transaction.atomic():
        audit = (
            AutoResolutionAudit.objects.select_for_update()
            .select_related("ticket")
            .get(pk=audit_id)
        )
        if audit.send_status == "sending":
            audit.decision = "agent_review"
            audit.decision_reason = "delivery_outcome_unknown"
            audit.send_status = "failed"
            audit.send_error = "delivery_outcome_unknown"
            audit.provider_result = "delivery_outcome_unknown"
            audit.save(
                update_fields=[
                    "decision",
                    "decision_reason",
                    "send_status",
                    "send_error",
                    "provider_result",
                    "updated_at",
                ]
            )
            return audit.send_status
        if audit.send_status != "pending":
            return audit.send_status

        config = get_auto_resolution_settings()
        if (
            not config.enabled
            or audit.channel != "whatsapp"
            or not config.whatsapp_auto_reply
        ):
            audit.decision = "agent_review"
            audit.decision_reason = "auto_resolution_disabled_before_send"
            audit.send_status = "not_sent"
            audit.save(
                update_fields=[
                    "decision",
                    "decision_reason",
                    "send_status",
                    "updated_at",
                ]
            )
            return audit.send_status
        if (
            audit.similarity_score is None
            or audit.ai_confidence is None
            or audit.similarity_score < config.minimum_threshold
            or audit.ai_confidence < config.minimum_threshold
        ):
            audit.decision = "agent_review"
            audit.decision_reason = "settings_or_threshold_changed_before_send"
            audit.send_status = "not_sent"
            audit.save(
                update_fields=[
                    "decision",
                    "decision_reason",
                    "send_status",
                    "updated_at",
                ]
            )
            return audit.send_status
        if config.simulation_mode:
            audit.decision = "simulation"
            audit.decision_reason = "simulation_mode"
            audit.send_status = "not_sent"
            audit.save(
                update_fields=[
                    "decision",
                    "decision_reason",
                    "send_status",
                    "updated_at",
                ]
            )
            return audit.send_status
        if audit.ticket.status != "open":
            audit.decision = "agent_review"
            audit.decision_reason = "ticket_no_longer_open"
            audit.send_status = "not_sent"
            audit.save(
                update_fields=[
                    "decision",
                    "decision_reason",
                    "send_status",
                    "updated_at",
                ]
            )
            return audit.send_status
        if settings.WHATSAPP_PROVIDER != "green_api":
            audit.decision = "agent_review"
            audit.decision_reason = "whatsapp_template_restricted"
            audit.send_status = "unavailable"
            audit.send_error = "generated_text_not_supported_by_template"
            audit.provider_result = "template_restricted"
            audit.save(
                update_fields=[
                    "decision",
                    "decision_reason",
                    "send_status",
                    "send_error",
                    "provider_result",
                    "updated_at",
                ]
            )
            return audit.send_status
        contact = CustomerContact.objects.filter(
            email__iexact=audit.ticket.requester_email
        ).first()
        if (
            not contact
            or not contact.whatsapp_consent
            or not contact.whatsapp_number
        ):
            audit.decision = "agent_review"
            audit.decision_reason = "whatsapp_consent_required"
            audit.send_status = "unavailable"
            audit.send_error = "whatsapp_consent_required"
            audit.provider_result = "green_api"
            audit.save(
                update_fields=[
                    "decision",
                    "decision_reason",
                    "send_status",
                    "send_error",
                    "provider_result",
                    "updated_at",
                ]
            )
            return audit.send_status
        if not configuration_ready():
            audit.decision = "agent_review"
            audit.decision_reason = "whatsapp_provider_unavailable"
            audit.send_status = "unavailable"
            audit.send_error = "provider_not_configured"
            audit.provider_result = "green_api"
            audit.save(
                update_fields=[
                    "decision",
                    "decision_reason",
                    "send_status",
                    "send_error",
                    "provider_result",
                    "updated_at",
                ]
            )
            return audit.send_status

        audit.send_status = "sending"
        audit.send_attempts += 1
        audit.provider_result = "green_api_attempted"
        audit.save(
            update_fields=["send_status", "send_attempts", "provider_result", "updated_at"]
        )
        recipient_number = contact.whatsapp_number

    try:
        state = get_state_instance()
    except Exception as exc:
        logger.warning(
            "Auto-resolution WhatsApp state check failed (audit_id=%s, error_type=%s)",
            audit_id,
            type(exc).__name__,
        )
        return _record_auto_resolution_whatsapp_failure(
            audit_id,
            error_code="green_api_state_check_failed",
            provider_result="green_api_state_check_failed",
        )
    if state.status != "authorized":
        error_code = (
            "green_api_not_authorized"
            if state.status == "notAuthorized"
            else f"green_api_{state.error_code or 'state_error'}"
        )
        return _record_auto_resolution_whatsapp_failure(
            audit_id,
            error_code=error_code,
            provider_result="green_api_state_check_failed",
        )

    try:
        result = send_whatsapp_message(recipient_number, audit.generated_response)
    except Exception as exc:
        logger.warning(
            "Auto-resolution WhatsApp send failed (audit_id=%s, error_type=%s)",
            audit_id,
            type(exc).__name__,
        )
        return _record_auto_resolution_whatsapp_failure(
            audit_id,
            error_code="green_api_send_failed",
            provider_result="green_api_delivery_failed",
        )
    if result.status != "sent":
        return _record_auto_resolution_whatsapp_failure(
            audit_id,
            error_code=result.error_code or "green_api_delivery_failed",
            provider_result="green_api_delivery_failed",
        )

    with transaction.atomic():
        audit = (
            AutoResolutionAudit.objects.select_for_update()
            .select_related("ticket")
            .get(pk=audit_id)
        )
        if audit.send_status != "sent":
            audit.send_status = "sent"
            audit.decision = "auto_sent"
            audit.decision_reason = "confidence_and_safety_checks_passed"
            audit.send_error = ""
            audit.provider_result = "green_api_accepted"
            audit.provider_message_id = result.message_id
            audit.save(
                update_fields=[
                    "send_status",
                    "decision",
                    "decision_reason",
                    "send_error",
                    "provider_result",
                    "provider_message_id",
                    "updated_at",
                ]
            )
            TicketMessage.objects.get_or_create(
                ticket=audit.ticket,
                ai_log=audit.ai_log,
                is_draft=False,
                defaults={
                    "body": audit.generated_response,
                    "message_type": "agent",
                    "is_ai_generated": True,
                },
            )
    return "sent"


def _record_auto_resolution_whatsapp_failure(
    audit_id: int, *, error_code: str, provider_result: str
) -> str:
    safe_error = error_code[:80]
    AutoResolutionAudit.objects.filter(pk=audit_id, send_status="sending").update(
        decision="agent_review",
        decision_reason="whatsapp_delivery_failed",
        send_status="failed",
        send_error=safe_error,
        provider_result=provider_result,
        updated_at=timezone.now(),
    )
    return "failed"


def enqueue_resolution_notification(notification_id: int) -> None:
    """Submit work without allowing broker errors to turn a committed ticket update into a 500."""
    try:
        send_resolution_notification_task.delay(notification_id)
    except Exception as exc:
        logger.warning("Resolution notification enqueue failed (notification_id=%s, error_type=%s)", notification_id, type(exc).__name__)
        ResolutionNotification.objects.filter(pk=notification_id, delivery_status="pending").update(
            delivery_status="failed", error_detail="queue_unavailable", next_attempt_at=None
        )


def enqueue_whatsapp_notification(notification_id: int) -> None:
    try:
        send_whatsapp_notification_task.delay(notification_id)
    except Exception as exc:
        logger.warning("WhatsApp enqueue failed (notification_id=%s, error_type=%s)", notification_id, type(exc).__name__)
        WhatsAppNotification.objects.filter(pk=notification_id, status="pending").update(
            status="failed", error_code="queue_unavailable", failed_at=timezone.now())


@shared_task(bind=True, max_retries=2)
def send_whatsapp_notification_task(self, notification_id: int) -> str:
    with transaction.atomic():
        notification = WhatsAppNotification.objects.select_for_update().select_related("ticket").get(pk=notification_id)
        if notification.status in ("sent", "delivered", "read", "queued"):
            return notification.status
        if notification.attempt_count >= WhatsAppNotification.MAX_ATTEMPTS:
            notification.status = "failed"
            notification.error_code = "retry_limit_reached"
            notification.failed_at = timezone.now()
            notification.save(update_fields=["status", "error_code", "failed_at"])
            return "failed"
        notification.status = "queued"
        notification.attempt_count += 1
        notification.last_attempt_at = timezone.now()
        notification.error_code = ""
        notification.error_detail = ""
        notification.save(update_fields=["status", "attempt_count", "last_attempt_at", "error_code", "error_detail"])
    if (not notification.customer or not notification.customer.whatsapp_consent or
            not notification.customer.whatsapp_number):
        notification.status = "failed"
        notification.error_code = "consent_required"
        notification.failed_at = timezone.now()
        notification.save(update_fields=["status", "error_code", "failed_at"])
        return "failed"
    from .services.whatsapp_service import normalize_whatsapp_number
    try:
        current_number = normalize_whatsapp_number(notification.customer.whatsapp_number)
    except ValueError:
        current_number = ""
    if current_number != notification.recipient_number:
        notification.recipient_number = current_number
        notification.save(update_fields=["recipient_number"])
    from .services.whatsapp_service import send_whatsapp_notification
    result = send_whatsapp_notification(notification)
    if result.success:
        notification.status = "sent"
        notification.meta_message_id = result.message_id
        notification.sent_at = timezone.now()
        notification.error_code = ""
        notification.save(update_fields=["status", "meta_message_id", "sent_at", "error_code"])
        return "sent"
    notification.error_code = result.error_code[:40]
    notification.error_detail = result.error_detail[:255]
    if result.transient and notification.attempt_count < WhatsAppNotification.MAX_ATTEMPTS and not current_app.conf.task_always_eager:
        from datetime import timedelta
        delay = 60 * (2 ** (notification.attempt_count - 1))
        notification.status = "pending"
        notification.save(update_fields=["status", "error_code", "error_detail"])
        raise self.retry(countdown=delay)
    notification.status = "failed"
    notification.failed_at = timezone.now()
    notification.save(update_fields=["status", "error_code", "error_detail", "failed_at"])
    return "failed"


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
