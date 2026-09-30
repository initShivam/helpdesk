from email.message import EmailMessage
from unittest.mock import patch

from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from tickets.models import Ticket, TicketMessage
from tickets.tasks import generate_ai_suggestion
from accounts.models import User

from .models import EmailAttachment, InboundEmail
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


@override_settings(MEDIA_ROOT="/tmp/helpdesk-email-tests")
class EmailIngestionTests(TestCase):
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

    @patch("email_ingestion.tasks.GmailImapClient")
    def test_fetch_marks_messages_seen_after_persisting(self, client_class):
        client = client_class.return_value.__enter__.return_value
        client.unread_messages.return_value = [
            (b"1", make_email()),
        ]

        result = fetch_emails()

        self.assertEqual(result, {"created": 1, "skipped": 0})
        client.mark_seen.assert_called_once_with(b"1")

    @patch("email_ingestion.imap_client.imaplib.IMAP4_SSL")
    def test_imap_client_runs_search_fetch_and_seen_protocol(self, imap_class):
        connection = imap_class.return_value
        connection.select.return_value = ("OK", [b""])
        connection.uid.side_effect = [
            ("OK", [b"7 8"]),
            ("OK", [(b"header", make_email(message_id="<imap-7@example.com>"))]),
            ("OK", [(b"header", make_email(message_id="<imap-8@example.com>"))]),
            ("OK", [b""]),
            ("OK", [b""]),
        ]

        with GmailImapClient(username="user", password="password") as client:
            messages = list(client.unread_messages())
            client.mark_seen(b"7")
            client.mark_seen(b"8")

        self.assertEqual([uid for uid, _ in messages], [b"7", b"8"])
        connection.login.assert_called_once_with("user", "password")
        connection.select.assert_called_once_with("INBOX")
        self.assertEqual(
            connection.uid.call_args_list[0].args,
            ("search", None, "UNSEEN"),
        )
        self.assertEqual(
            connection.uid.call_args_list[1].args,
            ("fetch", b"7", "(RFC822)"),
        )
        self.assertEqual(
            connection.uid.call_args_list[3].args,
            ("store", b"7", "+FLAGS", r"(\Seen)"),
        )
        connection.logout.assert_called_once_with()

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
    @patch("tickets.tasks.generate_with_gemini")
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
