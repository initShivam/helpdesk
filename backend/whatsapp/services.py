"""GREEN-API WhatsApp transport kept separate from ticket notification flows."""

from dataclasses import dataclass
import logging
import re
from urllib.parse import quote, urlsplit

import requests
from django.conf import settings


logger = logging.getLogger(__name__)

CONFIGURATION_KEYS = (
    "GREEN_API_URL",
    "GREEN_API_MEDIA_URL",
    "GREEN_API_INSTANCE_ID",
    "GREEN_API_TOKEN",
)


@dataclass(frozen=True)
class GreenApiResult:
    status: str
    message_id: str = ""
    error_code: str = ""


def validate_configuration() -> tuple[str, ...]:
    """Return missing/invalid setting names, never their values."""
    missing = [
        key for key in CONFIGURATION_KEYS
        if not str(getattr(settings, key, "") or "").strip()
    ]
    for key in ("GREEN_API_URL", "GREEN_API_MEDIA_URL"):
        value = str(getattr(settings, key, "") or "").strip()
        if value:
            try:
                parsed = urlsplit(value)
                valid_url = (
                    parsed.scheme in {"http", "https"}
                    and bool(parsed.netloc)
                    and parsed.username is None
                    and parsed.password is None
                    and not parsed.query
                    and not parsed.fragment
                )
            except ValueError:
                valid_url = False
            if not valid_url:
                missing.append(f"{key}_invalid")
    if int(getattr(settings, "GREEN_API_TIMEOUT_SECONDS", 0)) < 1:
        missing.append("GREEN_API_TIMEOUT_SECONDS_invalid")
    return tuple(missing)


def normalize_phone_number(phone_number: str) -> str:
    """Return Indian mobile numbers in GREEN-API's 91xxxxxxxxxx chat format."""
    digits = re.sub(r"[\s().-]", "", str(phone_number or ""))
    if digits.startswith("+"):
        digits = digits[1:]
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) == 10 and digits[0] in "6789":
        digits = f"91{digits}"
    elif len(digits) == 12 and digits.startswith("91") and digits[2] in "6789":
        pass
    else:
        raise ValueError("invalid_indian_phone_number")
    return digits


def _endpoint(method: str) -> str:
    problems = validate_configuration()
    if problems:
        raise ValueError("green_api_configuration_invalid:" + ",".join(problems))
    base_url = settings.GREEN_API_URL.rstrip("/")
    instance_id = quote(settings.GREEN_API_INSTANCE_ID, safe="")
    token = quote(settings.GREEN_API_TOKEN, safe="")
    return f"{base_url}/waInstance{instance_id}/{method}/{token}"


def get_state_instance() -> GreenApiResult:
    try:
        url = _endpoint("getStateInstance")
    except (AttributeError, TypeError, ValueError) as exc:
        return GreenApiResult("error", error_code=str(exc))

    try:
        response = requests.get(url, timeout=settings.GREEN_API_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        logger.warning("GREEN-API state request failed (error_type=%s)", type(exc).__name__)
        return GreenApiResult("error", error_code="network_error")
    if not response.ok:
        logger.warning("GREEN-API state request rejected (http_status=%s)", response.status_code)
        return GreenApiResult("error", error_code=f"http_{response.status_code}")
    try:
        state = response.json().get("stateInstance")
    except (AttributeError, ValueError):
        state = None
    if state == "authorized":
        return GreenApiResult("authorized")
    if state == "notAuthorized":
        return GreenApiResult("notAuthorized")
    logger.warning("GREEN-API returned an unexpected instance state")
    return GreenApiResult("error", error_code="unexpected_instance_state")


def send_whatsapp_message(phone_number: str, message: str) -> GreenApiResult:
    problems = validate_configuration()
    if problems:
        return GreenApiResult(
            "error",
            error_code="green_api_configuration_invalid:" + ",".join(problems),
        )
    try:
        normalized_number = normalize_phone_number(phone_number)
    except (TypeError, ValueError):
        return GreenApiResult("error", error_code="invalid_indian_phone_number")
    if not isinstance(message, str) or not message.strip() or len(message) > 4000:
        return GreenApiResult("error", error_code="invalid_message")
    try:
        url = _endpoint("sendMessage")
    except (AttributeError, TypeError, ValueError) as exc:
        return GreenApiResult("error", error_code=str(exc))

    try:
        response = requests.post(
            url,
            json={
                "chatId": f"{normalized_number}@c.us",
                "message": message.strip(),
            },
            timeout=settings.GREEN_API_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        logger.warning("GREEN-API send request failed (error_type=%s)", type(exc).__name__)
        return GreenApiResult("error", error_code="network_error")
    if not response.ok:
        logger.warning("GREEN-API send request rejected (http_status=%s)", response.status_code)
        return GreenApiResult("error", error_code=f"http_{response.status_code}")
    try:
        result = response.json()
    except ValueError:
        result = {}
    if not isinstance(result, dict):
        result = {}
    message_id = result.get("idMessage")
    if not isinstance(message_id, str) or not message_id:
        logger.warning("GREEN-API send response omitted message ID")
        return GreenApiResult("error", error_code="invalid_provider_response")
    return GreenApiResult("sent", message_id=message_id)
