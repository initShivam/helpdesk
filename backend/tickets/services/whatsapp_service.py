"""Twilio WhatsApp delivery with sanitized, structured outcomes."""
from dataclasses import dataclass
import json
import logging
import re

from django.conf import settings
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client


logger = logging.getLogger(__name__)


@dataclass
class WhatsAppResult:
    success: bool
    message_sid: str = ""
    error_code: str = ""
    transient: bool = False
    error_detail: str = ""


def _safe_provider_detail(value):
    detail = " ".join(str(value or "").split())
    if settings.TWILIO_AUTH_TOKEN:
        detail = detail.replace(settings.TWILIO_AUTH_TOKEN, "[redacted]")
    detail = re.sub(r"\b(?:AC|HX|SM)[0-9a-fA-F]{32}\b", "[redacted SID]", detail)
    detail = re.sub(r"\+?[0-9][0-9\s().-]{7,}[0-9]", "[redacted number]", detail)
    return detail[:255]


def normalize_whatsapp_number(value):
    value = (value or "").strip()
    if value.lower().startswith("whatsapp:"):
        value = value[9:]
    value = re.sub(r"[\s().-]", "", value)
    if not re.fullmatch(r"\+[1-9]\d{7,14}", value):
        raise ValueError("invalid_recipient")
    return value


def configuration_ready():
    return bool(settings.WHATSAPP_ENABLED and settings.WHATSAPP_PROVIDER == "twilio" and
                settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and
                settings.TWILIO_WHATSAPP_FROM and settings.WHATSAPP_TEMPLATE_SID)


def send_whatsapp_notification(notification):
    if not configuration_ready():
        return WhatsAppResult(False, error_code="provider_unavailable")
    try:
        recipient = normalize_whatsapp_number(notification.recipient_number)
        message = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN).messages.create(
            from_=settings.TWILIO_WHATSAPP_FROM,
            to=f"whatsapp:{recipient}",
            content_sid=settings.WHATSAPP_TEMPLATE_SID,
            content_variables=notification.content_variables,
            status_callback=settings.TWILIO_STATUS_CALLBACK_URL or None,
        )
        return WhatsAppResult(True, message_sid=message.sid or "")
    except ValueError:
        return WhatsAppResult(False, error_code="invalid_recipient")
    except Exception as exc:
        # Keep provider text out of logs and API responses. Classify only known retryable cases.
        code = getattr(exc, "code", None)
        status_code = getattr(exc, "status", None)
        is_twilio = isinstance(exc, TwilioRestException)
        if is_twilio:
            transient = status_code == 429 or (status_code is not None and status_code >= 500)
            if status_code == 429:
                error = "rate_limited"
            elif transient:
                error = "provider_unavailable"
            elif isinstance(code, int) and code > 0:
                error = f"twilio_{code}"
            else:
                error = f"provider_rejected_{status_code}" if status_code else "provider_rejected"
            logger.warning(
                "Twilio WhatsApp request rejected (http_status=%s, twilio_code=%s)",
                status_code,
                code if isinstance(code, int) and code > 0 else "unavailable",
            )
            error_detail = _safe_provider_detail(getattr(exc, "msg", ""))
        else:
            transient = True
            error = "network_error"
            error_detail = ""
        return WhatsAppResult(False, error_code=error, transient=transient, error_detail=error_detail)
