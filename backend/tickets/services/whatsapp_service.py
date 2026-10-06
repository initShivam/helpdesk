"""Meta WhatsApp Cloud API delivery with sanitized, structured outcomes."""
from dataclasses import dataclass
import logging
import re

from django.conf import settings
import requests


logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v25.0"


@dataclass
class WhatsAppResult:
    success: bool
    message_id: str = ""
    error_code: str = ""
    transient: bool = False
    error_detail: str = ""


def _access_token():
    token = (settings.META_WHATSAPP_ACCESS_TOKEN or "").strip()
    if len(token) >= 2 and token[0] in ("'", '"') and token[-1] == token[0]:
        token = token[1:-1].strip()
    return token


def safe_provider_detail(value):
    detail = " ".join(str(value or "").split())
    for secret in (
        _access_token(),
        settings.META_WHATSAPP_PHONE_NUMBER_ID,
        settings.META_WHATSAPP_BUSINESS_ACCOUNT_ID,
    ):
        if secret:
            detail = detail.replace(secret, "[redacted]")
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
    if not settings.WHATSAPP_ENABLED:
        return False
    if settings.WHATSAPP_PROVIDER == "green_api":
        from whatsapp.services import validate_configuration

        return not validate_configuration()
    if settings.WHATSAPP_PROVIDER == "meta":
        return bool(
            _access_token()
            and settings.META_WHATSAPP_PHONE_NUMBER_ID
            and settings.META_WHATSAPP_TEMPLATE_NAME
            and settings.META_WHATSAPP_TEMPLATE_LANGUAGE
        )
    return False


def _provider_failure(status_code, error):
    code = error.get("code")
    subcode = error.get("error_subcode")
    transient = bool(error.get("is_transient")) or status_code == 429 or status_code >= 500
    if code in (4, 17, 32, 613):
        transient = True
    if status_code == 429:
        error_code = "rate_limited"
    elif transient:
        error_code = "provider_unavailable"
    elif isinstance(code, int) and code > 0:
        error_code = f"meta_{code}"
        if isinstance(subcode, int) and subcode > 0:
            error_code = f"meta_{code}_{subcode}"
    else:
        error_code = f"provider_rejected_{status_code}" if status_code else "provider_rejected"
    return WhatsAppResult(
        False,
        error_code=error_code,
        transient=transient,
        error_detail=safe_provider_detail(error.get("message", "")),
    )


def send_whatsapp_notification(notification):
    if not configuration_ready():
        return WhatsAppResult(
            False,
            error_code="provider_unavailable",
            error_detail="WhatsApp provider is not fully configured.",
        )
    if settings.WHATSAPP_PROVIDER == "green_api":
        return _send_green_api_notification(notification)

    try:
        recipient = normalize_whatsapp_number(notification.recipient_number)
    except ValueError:
        return WhatsAppResult(False, error_code="invalid_recipient")

    payload = {
        "messaging_product": "whatsapp",
        "to": recipient[1:],
        "type": "template",
        "template": {
            "name": settings.META_WHATSAPP_TEMPLATE_NAME,
            "language": {"code": settings.META_WHATSAPP_TEMPLATE_LANGUAGE},
        },
    }
    token = _access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{settings.META_WHATSAPP_PHONE_NUMBER_ID}/messages"
    logger.info(
        "Meta WhatsApp auth config (token_configured=%s, token_length=%s, phone_number_id=%s, api_version=%s)",
        bool(token),
        len(token),
        settings.META_WHATSAPP_PHONE_NUMBER_ID,
        GRAPH_API_VERSION,
    )
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
    except requests.RequestException as exc:
        logger.warning("Meta WhatsApp request failed (error_type=%s)", type(exc).__name__)
        return WhatsAppResult(False, error_code="network_error", transient=True)

    try:
        result = response.json()
    except ValueError:
        result = {}
    if not isinstance(result, dict):
        result = {}
    if not response.ok:
        error = result.get("error") or {}
        logger.warning(
            "Meta WhatsApp request rejected (http_status=%s, meta_code=%s)",
            response.status_code,
            error.get("code") if isinstance(error.get("code"), int) else "unavailable",
        )
        return _provider_failure(response.status_code, error)
    try:
        message_id = (result.get("messages") or [{}])[0].get("id", "")
        if not message_id:
            logger.warning("Meta WhatsApp response omitted message ID")
            return WhatsAppResult(False, error_code="provider_rejected")
        return WhatsAppResult(True, message_id=message_id)
    except (AttributeError, IndexError, TypeError):
        logger.warning("Meta WhatsApp response omitted message ID")
        return WhatsAppResult(False, error_code="provider_rejected")


def _send_green_api_notification(notification):
    from whatsapp.services import get_state_instance, send_whatsapp_message

    state = get_state_instance()
    if state.status != "authorized":
        error_code = (
            "green_api_not_authorized"
            if state.status == "notAuthorized"
            else f"green_api_{state.error_code or 'state_error'}"
        )
        return WhatsAppResult(
            False,
            error_code=error_code[:40],
            transient=state.error_code in {
                "network_error",
                "http_429",
                "http_500",
                "http_502",
                "http_503",
                "http_504",
            },
            error_detail=(
                "GREEN-API instance is not authorized."
                if state.status == "notAuthorized"
                else "GREEN-API instance status could not be verified."
            ),
        )

    ticket = notification.ticket
    message = (
        f"Your support ticket #{ticket.ticket_number} has been resolved. "
        "Please contact our support team if you need any further assistance."
    )
    result = send_whatsapp_message(notification.recipient_number, message)
    if result.status == "sent":
        return WhatsAppResult(True, message_id=result.message_id)
    transient = result.error_code in {
        "network_error",
        "http_429",
        "http_500",
        "http_502",
        "http_503",
        "http_504",
    }
    return WhatsAppResult(
        False,
        error_code=f"green_api_{result.error_code}"[:40],
        transient=transient,
        error_detail="GREEN-API could not send the WhatsApp message.",
    )
