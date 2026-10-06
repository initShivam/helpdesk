import logging
from threading import Lock
from uuid import uuid4

from celery import shared_task
from django.core.files.base import ContentFile
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from .imap_client import GmailImapClient
from .models import EmailAttachment, InboundEmail, MailboxSyncState
from .parser import ParsedEmail, parse_email
from tickets.ai import enrich_ticket
from tickets.models import Ticket, TicketMessage
from tickets.tasks import enqueue_auto_resolution

logger = logging.getLogger(__name__)
_mailbox_sync_lock = Lock()


def _ticket_number() -> str:
    return f"EMAIL-{uuid4().hex[:14].upper()}"


@transaction.atomic
def persist_email(parsed: ParsedEmail) -> tuple[InboundEmail, bool]:
    existing = InboundEmail.objects.filter(message_id=parsed.message_id).first()
    if existing:
        return existing, False

    ticket = None
    ticket_created = False
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
            description=parsed.body or '',
            requester_email=parsed.sender_email,
            source="email",
        )
        ticket_created = True

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
    if ticket_created:
        transaction.on_commit(
            lambda ticket_id=ticket.pk: enqueue_auto_resolution(ticket_id)
        )
    return inbound, True


@shared_task
def fetch_emails() -> dict[str, int]:
    # Keep same-process Refresh requests and the local poller serialized. The
    # database row lock below also serializes workers in other processes.
    with _mailbox_sync_lock:
        result = {"matched": 0, "created": 0, "skipped": 0, "errors": 0}
        with GmailImapClient() as client:
            with transaction.atomic():
                if connection.vendor == "sqlite":
                    # Acquire SQLite's writer lock before reading state. A later
                    # no-op update could otherwise race on a stale read snapshot.
                    MailboxSyncState.objects.filter(
                        mailbox=client.mailbox,
                        account_fingerprint=client.account_fingerprint,
                    ).update(updated_at=timezone.now())
                state, state_created = MailboxSyncState.objects.select_for_update().get_or_create(
                    mailbox=client.mailbox,
                    account_fingerprint=client.account_fingerprint,
                    defaults={
                        "uid_validity": client.uid_validity,
                        # FROM_NOW: don't backfill the existing mailbox.
                        "last_processed_uid": max(0, (client.uid_next or 1) - 1),
                    },
                )
                cursor_reset = False
                if state_created:
                    state = MailboxSyncState.objects.select_for_update().get(pk=state.pk)
                    logger.info(
                        "mailbox_cursor_initialized mailbox=%s uid_validity=%s last_processed_uid=%s mode=FROM_NOW",
                        state.mailbox,
                        state.uid_validity,
                        state.last_processed_uid,
                    )
                elif state.uid_validity != client.uid_validity:
                    old_validity = state.uid_validity
                    state.uid_validity = client.uid_validity
                    state.last_processed_uid = max(0, (client.uid_next or 1) - 1)
                    state.save(update_fields=["uid_validity", "last_processed_uid", "updated_at"])
                    cursor_reset = True
                    logger.warning(
                        "mailbox_uidvalidity_changed mailbox=%s old_uid_validity=%s new_uid_validity=%s cursor_reset=%s",
                        state.mailbox,
                        old_validity,
                        state.uid_validity,
                        state.last_processed_uid,
                    )
                uids = [] if cursor_reset else client.search_uids_after(state.last_processed_uid)
                result["matched"] = len(uids)
                for uid in uids:
                    uid_text = uid.decode(errors="replace")
                    parsed = None
                    try:
                        logger.info("mailbox_message_processing mailbox=%s uid=%s", state.mailbox, uid_text)
                        raw_message = client.fetch_message(uid)
                        parsed = parse_email(raw_message)
                        logger.info(
                            "mailbox_message_parsed mailbox=%s uid=%s message_id=%s",
                            state.mailbox,
                            uid_text,
                            parsed.message_id,
                        )
                        try:
                            _, was_created = persist_email(parsed)
                        except IntegrityError:
                            # Another sync may have persisted the same RFC Message-ID.
                            if not InboundEmail.objects.filter(message_id=parsed.message_id).exists():
                                raise
                            was_created = False

                        if was_created:
                            result["created"] += 1
                            logger.info(
                                "mailbox_message_persisted mailbox=%s uid=%s message_id=%s created=true",
                                state.mailbox,
                                uid_text,
                                parsed.message_id,
                            )
                        else:
                            result["skipped"] += 1
                            logger.info(
                                "mailbox_message_duplicate_skipped mailbox=%s uid=%s message_id=%s",
                                state.mailbox,
                                uid_text,
                                parsed.message_id,
                            )

                        # This is retained for compatibility; fetching RFC822 may
                        # already set Seen, but it is no longer used as a cursor.
                        client.mark_seen(uid)
                        with transaction.atomic():
                            MailboxSyncState.objects.filter(
                                pk=state.pk,
                                uid_validity=client.uid_validity,
                                last_processed_uid__lt=int(uid),
                            ).update(
                                last_processed_uid=int(uid),
                                updated_at=timezone.now(),
                            )
                            state.refresh_from_db()
                        logger.info(
                            "mailbox_cursor_advanced mailbox=%s uid=%s message_id=%s",
                            state.mailbox,
                            uid_text,
                            parsed.message_id,
                        )
                    except Exception:
                        result["errors"] += 1
                        logger.exception(
                            "mailbox_message_failed mailbox=%s uid=%s message_id=%s cursor_unchanged=%s",
                            state.mailbox,
                            uid_text,
                            parsed.message_id if parsed else "unknown",
                            state.last_processed_uid,
                        )
                        break

        logger.info(
            "mailbox_sync_complete mailbox=%s matched=%s created=%s skipped=%s errors=%s",
            client.mailbox,
            result["matched"],
            result["created"],
            result["skipped"],
            result["errors"],
        )
        return result
