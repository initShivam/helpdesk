from unittest.mock import patch

from django.core import mail
from django.db import transaction
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from tickets.models import ResolutionNotification, Ticket
from tickets.tasks import send_resolution_notification_task


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="support@example.com",
    EMAIL_HOST_USER="support@example.com",
    EMAIL_HOST_PASSWORD="test-only",
)
class ResolutionEmailTests(TestCase):
    def setUp(self):
        self.agent = User.objects.create_user(username="agent", password="pass", role="AGENT")
        self.client = APIClient()
        self.client.force_authenticate(self.agent)
        self.ticket = Ticket.objects.create(
            ticket_number="HD-1001", subject="Cannot sign in", requester_email="customer@example.com",
        )

    def resolve(self, note=""):
        return self.client.patch(
            f"/api/tickets/{self.ticket.pk}/", {"status": "resolved", "resolution_note": note}, format="json"
        )

    def test_successful_resolution_sends_text_and_html_email(self):
        self.resolve("Password reset completed.")
        notification = ResolutionNotification.objects.get(ticket=self.ticket)
        self.assertEqual(send_resolution_notification_task(notification.pk), "sent")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["customer@example.com"])
        self.assertIn("#HD-1001", mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].alternatives[0][1], "text/html")

    def test_unrelated_update_does_not_notify(self):
        self.client.patch(f"/api/tickets/{self.ticket.pk}/", {"priority": "high"}, format="json")
        self.assertFalse(ResolutionNotification.objects.exists())

    def test_invalid_recipient_is_recorded_failed_without_sending(self):
        Ticket.objects.filter(pk=self.ticket.pk).update(requester_email="bad address")
        self.resolve()
        notification = ResolutionNotification.objects.get(ticket=self.ticket)
        self.assertEqual(send_resolution_notification_task(notification.pk), "failed")
        self.assertEqual(notification.__class__.objects.get(pk=notification.pk).error_detail, "invalid_address")
        self.assertFalse(mail.outbox)

    def test_duplicate_resolved_patch_does_not_create_duplicate(self):
        self.resolve()
        self.client.patch(f"/api/tickets/{self.ticket.pk}/", {"status": "resolved"}, format="json")
        self.assertEqual(ResolutionNotification.objects.filter(ticket=self.ticket).count(), 1)

    def test_reopen_then_resolve_creates_new_event(self):
        self.resolve()
        self.client.patch(f"/api/tickets/{self.ticket.pk}/", {"status": "open"}, format="json")
        self.resolve()
        self.assertEqual(ResolutionNotification.objects.filter(ticket=self.ticket).count(), 2)

    def test_smtp_failure_is_sanitized_and_bounded(self):
        self.resolve()
        notification = ResolutionNotification.objects.get(ticket=self.ticket)
        notification.attempt_count = 2
        notification.save(update_fields=["attempt_count"])
        with patch("tickets.services.outbound_email.send_resolution_notification", side_effect=RuntimeError("private SMTP details")):
            self.assertEqual(send_resolution_notification_task(notification.pk), "failed")
        notification.refresh_from_db()
        self.assertEqual(notification.error_detail, "smtp_delivery_failed")
        self.assertNotIn("private", notification.error_detail)

    def test_retry_sends_failed_notification(self):
        self.resolve()
        notification = ResolutionNotification.objects.get(ticket=self.ticket)
        notification.delivery_status = "failed"
        notification.attempt_count = 1
        notification.save(update_fields=["delivery_status", "attempt_count"])
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f"/api/tickets/{self.ticket.pk}/retry-resolution-notification/")
        self.assertEqual(response.status_code, 202)
        notification.refresh_from_db()
        self.assertEqual(notification.delivery_status, "sent")

    def test_broker_failure_is_recorded_without_failing_ticket_update(self):
        with patch("tickets.tasks.send_resolution_notification_task.delay", side_effect=RuntimeError("broker detail")):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.resolve()
        self.assertEqual(response.status_code, 200)
        notification = ResolutionNotification.objects.get(ticket=self.ticket)
        self.assertEqual(notification.delivery_status, "failed")
        self.assertEqual(notification.error_detail, "queue_unavailable")

    def test_unauthorized_user_cannot_resolve_or_retry(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.resolve().status_code, 401)
        self.assertEqual(self.client.post(f"/api/tickets/{self.ticket.pk}/retry-resolution-notification/").status_code, 401)

    def test_database_rollback_does_not_dispatch_email(self):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    self.resolve()
                    raise RuntimeError("rollback")
        self.assertEqual(callbacks, [])
        self.assertFalse(ResolutionNotification.objects.exists())
