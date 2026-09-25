from uuid import uuid4

from celery import shared_task
from django.core.files.base import ContentFile
from django.db import transaction

from .imap_client import GmailImapClient
from .models import EmailAttachment, InboundEmail
from .parser import ParsedEmail, parse_email
from tickets.ai import enrich_ticket
from tickets.models import Ticket, TicketMessage


def _ticket_number() -> str:
    return f"EMAIL-{uuid4().hex[:14].upper()}"


@transaction.atomic
def persist_email(parsed: ParsedEmail) -> tuple[InboundEmail, bool]:
    existing = InboundEmail.objects.filter(message_id=parsed.message_id).first()
    if existing:
        return existing, False

    ticket = None
    if parsed.thread_id:
        ticket = (
            Ticket.objects.filter(inbound_emails__thread_id=parsed.thread_id)
            .order_by("created_at")
            .first()
        )
    if ticket is None:
        ticket = Ticket.objects.create(
            ticket_number=_ticket_number(),
            subject=(parsed.subject or "(no subject)")[:255],
            requester_email=parsed.sender_email,
            source="email",
        )

    message = TicketMessage.objects.create(
        ticket=ticket,
        body=parsed.body or "(empty message)",
        message_type="customer",
    )
    enrich_ticket(ticket, parsed.body)
    inbound = InboundEmail.objects.create(
        message_id=parsed.message_id,
        thread_id=parsed.thread_id,
        sender_email=parsed.sender_email,
        subject=parsed.subject,
        received_at=parsed.received_at,
        ticket=ticket,
        ticket_message=message,
    )
    for attachment in parsed.attachments:
        stored = EmailAttachment.objects.create(
            inbound_email=inbound,
            filename=attachment.filename,
            content_type=attachment.content_type,
            size_bytes=len(attachment.content),
        )
        stored.file.save(
            attachment.filename,
            ContentFile(attachment.content),
            save=True,
        )
    return inbound, True


@shared_task
def fetch_emails() -> dict[str, int]:
    created = 0
    skipped = 0
    with GmailImapClient() as client:
        for uid, raw_message in client.unread_messages():
            parsed = parse_email(raw_message)
            _, was_created = persist_email(parsed)
            if was_created:
                created += 1
            else:
                skipped += 1
            client.mark_seen(uid)
    return {"created": created, "skipped": skipped}
