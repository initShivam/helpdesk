from email.message import EmailMessage
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
import tempfile
from unittest.mock import patch

from django.core.files.storage import default_storage
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from tickets.models import Ticket, TicketMessage
from tickets.tasks import generate_ai_suggestion
from accounts.models import User

from .models import EmailAttachment, InboundEmail, MailboxSyncState
from .parser import parse_email
from .tasks import fetch_emails, persist_email
from .imap_client import GmailImapClient


def make_email(
    message_id="<message-1@example.com>",
    subject="Printer issue",
    thread_id="",
    attachment=False,
    body="The printer is not working.",
):
    message = EmailMessage()
    message["From"] = "Customer <customer@example.com>"
    message["To"] = "support@example.com"
    message["Subject"] = subject
    message["Message-ID"] = message_id
    if thread_id:
        message["References"] = thread_id
    message.set_content(body)
    if attachment:
        message.add_attachment(
            b"file contents",
            maintype="text",
            subtype="plain",
            filename="details.txt",
        )
    return message.as_bytes()


@override_settings(MEDIA_ROOT=str(Path(tempfile.gettempdir()) / "helpdesk-email-tests"))
class EmailIngestionTests(TestCase):
    def prepare_mailbox(self, client_class, uids=(b"1",), uid_next=2, uid_validity=7):
        client = client_class.return_value.__enter__.return_value
        client.mailbox = "INBOX"
        client.account_fingerprint = "test-account"
        client.uid_validity = uid_validity
        client.uid_next = uid_next
        client.search_uids_after.return_value = list(uids)
        client.fetch_message.side_effect = lambda uid: make_email(
            message_id=f"<message-{uid.decode()}@example.com>"
        )
        MailboxSyncState.objects.create(
            mailbox="INBOX",
            account_fingerprint="test-account",
            uid_validity=uid_validity,
            last_processed_uid=0,
        )
        return client

    def tearDown(self):
        for attachment in EmailAttachment.objects.all():
            if attachment.file:
                default_storage.delete(attachment.file.name)

    def test_parser_extracts_sender_body_thread_and_attachment(self):
        parsed = parse_email(
            make_email(thread_id="<original@example.com>", attachment=True)
        )
        self.assertEqual(parsed.message_id, "<message-1@example.com>")
        self.assertEqual(parsed.thread_id, "<original@example.com>")
        self.assertEqual(parsed.sender_email, "customer@example.com")
        self.assertEqual(parsed.body, "The printer is not working.")
        self.assertEqual(parsed.attachments[0].filename, "details.txt")

    def test_parser_rejects_missing_sender(self):
        raw = make_email().replace(
            b"From: Customer <customer@example.com>",
            b"From: ",
        )
        with self.assertRaises(ValueError):
            parse_email(raw)

    def test_persist_email_is_idempotent_and_reuses_thread_ticket(self):
        first, created = persist_email(parse_email(make_email()))
        duplicate, duplicate_created = persist_email(parse_email(make_email()))
        reply, reply_created = persist_email(
            parse_email(
                make_email(
                    message_id="<message-2@example.com>",
                    thread_id="<message-1@example.com>",
                )
            )
        )

        self.assertTrue(created)
        self.assertFalse(duplicate_created)
        self.assertTrue(reply_created)
        self.assertEqual(first.pk, duplicate.pk)
        self.assertEqual(first.ticket_id, reply.ticket_id)
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertEqual(TicketMessage.objects.count(), 2)
        self.assertEqual(InboundEmail.objects.count(), 2)
        ticket = Ticket.objects.get(pk=first.ticket_id)
        self.assertEqual(ticket.category, "technical")
        self.assertTrue(ticket.ai_summary)
        self.assertIsNotNone(ticket.ai_category_confidence)
        self.assertLessEqual(len(ticket.ai_summary), 240)

    @patch("email_ingestion.tasks.enrich_ticket")
    @patch("email_ingestion.tasks.GmailImapClient")
    def test_seen_email_is_imported(self, client_class, enrich):
        client = self.prepare_mailbox(client_class)

        result = fetch_emails()

        self.assertEqual(result, {"matched": 1, "created": 1, "skipped": 0, "errors": 0})
        self.assertEqual(InboundEmail.objects.count(), 1)
        client.mark_seen.assert_called_once_with(b"1")

    @patch("email_ingestion.tasks.enrich_ticket")
    @patch("email_ingestion.tasks.GmailImapClient")
    def test_unseen_email_is_imported(self, client_class, enrich):
        self.prepare_mailbox(client_class, uids=(b"2",), uid_next=3)

        result = fetch_emails()

        self.assertEqual(result, {"matched": 1, "created": 1, "skipped": 0, "errors": 0})
        self.assertTrue(InboundEmail.objects.filter(message_id="<message-2@example.com>").exists())

    @patch("email_ingestion.tasks.enrich_ticket")
    @patch("email_ingestion.tasks.GmailImapClient")
    def test_existing_message_id_is_skipped_and_cursor_advances(self, client_class, enrich):
        inbound, _ = persist_email(parse_email(make_email()))
        self.prepare_mailbox(client_class)

        result = fetch_emails()

        self.assertEqual(result, {"matched": 1, "created": 0, "skipped": 1, "errors": 0})
        self.assertEqual(InboundEmail.objects.count(), 1)
        self.assertEqual(TicketMessage.objects.filter(ticket=inbound.ticket).count(), 1)
        self.assertEqual(MailboxSyncState.objects.get(mailbox="INBOX", account_fingerprint="test-account").last_processed_uid, 1)

    @patch("email_ingestion.tasks.persist_email", side_effect=RuntimeError("database unavailable"))
    @patch("email_ingestion.tasks.GmailImapClient")
    def test_failed_persistence_does_not_advance_cursor(self, client_class, persist):
        self.prepare_mailbox(client_class)

        result = fetch_emails()

        self.assertEqual(result, {"matched": 1, "created": 0, "skipped": 0, "errors": 1})
        self.assertEqual(MailboxSyncState.objects.get(mailbox="INBOX", account_fingerprint="test-account").last_processed_uid, 0)

    @patch("email_ingestion.imap_client.imaplib.IMAP4_SSL")
    def test_imap_client_searches_uid_range_without_seen_filter(self, imap_class):
        connection = imap_class.return_value
        connection.select.return_value = ("OK", [b""])
        connection.status.return_value = ("OK", [b"INBOX (UIDVALIDITY 123 UIDNEXT 9)"])
        connection.uid.return_value = ("OK", [b"8 7"])

        with GmailImapClient(username="user", password="password") as client:
            uids = client.search_uids_after(6)
            self.assertEqual(client.search_uids_after(8), [])

        self.assertEqual(uids, [b"7", b"8"])
        self.assertEqual((client.uid_validity, client.uid_next), (123, 9))
        connection.login.assert_called_once_with("user", "password")
        connection.select.assert_called_once_with("INBOX")
        connection.status.assert_called_once_with("INBOX", "(UIDVALIDITY UIDNEXT)")
        self.assertEqual(
            connection.uid.call_args_list[0].args,
            ("search", None, "UID", "7:8"),
        )
        self.assertEqual(connection.uid.call_count, 1)
        connection.logout.assert_called_once_with()

    @patch("email_ingestion.tasks.GmailImapClient")
    def test_uidvalidity_change_reinitializes_cursor_from_now(self, client_class):
        MailboxSyncState.objects.create(
            mailbox="INBOX",
            account_fingerprint="test-account",
            uid_validity=6,
            last_processed_uid=100,
        )
        client = client_class.return_value.__enter__.return_value
        client.mailbox = "INBOX"
        client.account_fingerprint = "test-account"
        client.uid_validity = 7
        client.uid_next = 5

        result = fetch_emails()

        state = MailboxSyncState.objects.get(mailbox="INBOX", account_fingerprint="test-account")
        self.assertEqual(result, {"matched": 0, "created": 0, "skipped": 0, "errors": 0})
        self.assertEqual((state.uid_validity, state.last_processed_uid), (7, 4))
        client.search_uids_after.assert_not_called()

    @patch("email_ingestion.tasks.GmailImapClient")
    def test_empty_uid_range_returns_zero_matched(self, client_class):
        client = self.prepare_mailbox(client_class, uids=(), uid_next=1)

        result = fetch_emails()

        self.assertEqual(result, {"matched": 0, "created": 0, "skipped": 0, "errors": 0})
        client.search_uids_after.assert_called_once_with(0)
        self.assertEqual(MailboxSyncState.objects.get(mailbox="INBOX", account_fingerprint="test-account").last_processed_uid, 0)

    @patch("email_ingestion.tasks.GmailImapClient")
    def test_first_sync_initializes_cursor_from_now(self, client_class):
        client = client_class.return_value.__enter__.return_value
        client.mailbox = "INBOX"
        client.account_fingerprint = "test-account"
        client.uid_validity = 7
        client.uid_next = 28

        result = fetch_emails()

        state = MailboxSyncState.objects.get(mailbox="INBOX", account_fingerprint="test-account")
        self.assertEqual(result, {"matched": 0, "created": 0, "skipped": 0, "errors": 0})
        self.assertEqual(state.last_processed_uid, 27)
        client.search_uids_after.assert_called_once_with(27)

    def test_email_priority_is_calculated_from_urgency(self):
        inbound, created = persist_email(
            parse_email(
                make_email(
                    message_id="<urgent@example.com>",
                    subject="Exam portal outage",
                    body="The system is down and my exam is today. Please help ASAP.",
                )
            )
        )

        self.assertTrue(created)
        inbound.ticket.refresh_from_db()
        self.assertEqual(inbound.ticket.priority, "high")

    def test_celery_discovers_fetch_task(self):
        from helpdesk.celery import app

        app.loader.import_task_module("email_ingestion.tasks")
        self.assertIn("email_ingestion.tasks.fetch_emails", app.tasks)

    @patch("tickets.tasks.retrieve", return_value=[])
    @patch("tickets.tasks.generate_with_openai")
    def test_email_to_ticket_to_ai_suggestion_flow(self, generate, retrieve):
        generate.return_value = (
            "Please restart the printer and try again. We can investigate further if the issue continues.",
            {"totalTokenCount": 18},
        )

        inbound, created = persist_email(
            parse_email(
                make_email(
                    message_id="<phase3-flow@example.com>",
                    subject="Printer is not working",
                    body="The office printer is broken and I need help urgently.",
                )
            )
        )
        log_id = generate_ai_suggestion.run(inbound.ticket_id)

        inbound.ticket.refresh_from_db()
        suggestion = TicketMessage.objects.get(
            ticket=inbound.ticket,
            ai_log_id=log_id,
            is_ai_generated=True,
            is_draft=True,
        )
        self.assertTrue(created)
        self.assertEqual(inbound.ticket.source, "email")
        self.assertEqual(inbound.ticket.messages.filter(message_type="customer").count(), 1)
        self.assertIn("restart the printer", suggestion.body)
        self.assertEqual(suggestion.ai_log.response_text, suggestion.body)
        generate.assert_called_once()

    def test_attachment_is_exposed_and_downloadable_for_ticket(self):
        user = User.objects.create_user(username="attachment-agent", password="pass", role="AGENT")
        inbound, _ = persist_email(parse_email(make_email(attachment=True)))
        client = APIClient()
        client.force_authenticate(user=user)

        detail = client.get(f"/api/tickets/{inbound.ticket_id}/")
        self.assertEqual(detail.status_code, 200)
        attachment = detail.data["attachments"][0]
        self.assertEqual(attachment["filename"], "details.txt")

        response = client.get(attachment["download_url"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Disposition"], 'attachment; filename="details.txt"')
        self.assertEqual(b"".join(response.streaming_content), b"file contents")


class EmailIngestionConcurrencyTests(TransactionTestCase):
    @patch("email_ingestion.tasks.enrich_ticket")
    @patch("email_ingestion.tasks.GmailImapClient")
    def test_concurrent_syncs_do_not_duplicate_or_regress_cursor(self, client_class, enrich):
        MailboxSyncState.objects.create(
            mailbox="INBOX",
            account_fingerprint="test-account",
            uid_validity=7,
            last_processed_uid=0,
        )
        client = client_class.return_value.__enter__.return_value
        client.mailbox = "INBOX"
        client.account_fingerprint = "test-account"
        client.uid_validity = 7
        client.uid_next = 2
        client.search_uids_after.side_effect = lambda cursor: [b"1"] if cursor < 1 else []
        client.fetch_message.return_value = make_email()

        start = Barrier(3)

        def sync_with_separate_connection():
            close_old_connections()
            start.wait()
            try:
                return fetch_emails()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(sync_with_separate_connection)
            second = executor.submit(sync_with_separate_connection)
            start.wait()
            results = [first.result(timeout=10), second.result(timeout=10)]

        self.assertEqual(sum(result["created"] for result in results), 1)
        self.assertEqual(sum(result["errors"] for result in results), 0)
        self.assertEqual(InboundEmail.objects.count(), 1)
        self.assertEqual(MailboxSyncState.objects.get(mailbox="INBOX", account_fingerprint="test-account").last_processed_uid, 1)
