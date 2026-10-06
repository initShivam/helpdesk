from celery import shared_task

from .services import get_state_instance, send_whatsapp_message


@shared_task
def send_whatsapp_message_task(phone_number: str, message: str) -> dict[str, str]:
    """Send through GREEN-API after confirming its instance is authorized."""
    state = get_state_instance()
    if state.status != "authorized":
        return {
            "status": state.status,
            "error_code": state.error_code or "instance_not_authorized",
        }
    result = send_whatsapp_message(phone_number, message)
    return {
        "status": result.status,
        "message_id": result.message_id,
        "error_code": result.error_code,
    }
