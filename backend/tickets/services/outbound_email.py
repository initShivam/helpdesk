from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.template.loader import render_to_string


def send_resolution_notification(notification):
    recipient = notification.recipient_email.strip()
    sender = settings.DEFAULT_FROM_EMAIL.strip()
    if any(character in recipient + sender for character in "\r\n"):
        raise ValueError("invalid_address")
    validate_email(recipient)
    validate_email(sender)
    message = EmailMultiAlternatives(
        subject=notification.subject,
        body=render_to_string("tickets/email/resolution.txt", {"notification": notification}),
        from_email=sender,
        to=[recipient],
        reply_to=[sender],
    )
    message.attach_alternative(
        render_to_string("tickets/email/resolution.html", {"notification": notification}),
        "text/html",
    )
    return message.send(fail_silently=False)
