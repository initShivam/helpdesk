from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from tickets.models import CustomerContact, Ticket, WhatsAppNotification
from tickets.services.whatsapp_service import normalize_whatsapp_number, send_whatsapp_notification
from tickets.tasks import send_whatsapp_notification_task
from twilio.base.exceptions import TwilioRestException


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
                   DEFAULT_FROM_EMAIL="support@example.com", EMAIL_HOST_USER="support@example.com", EMAIL_HOST_PASSWORD="test")
class WhatsAppIntegrationTests(TestCase):
    def setUp(self):
        self.agent = User.objects.create_user(username="wa-agent", password="pass", role="AGENT")
        self.client = APIClient()
        self.client.force_authenticate(self.agent)
        self.ticket = Ticket.objects.create(ticket_number="WA-100", subject="Account help", requester_email="wa@example.com")

    def test_phone_normalization(self):
        self.assertEqual(normalize_whatsapp_number(" +1 (415) 555-0123 "), "+14155550123")
        with self.assertRaises(ValueError):
            normalize_whatsapp_number("4155550123")

    @override_settings(WHATSAPP_ENABLED=True, WHATSAPP_PROVIDER="twilio", TWILIO_ACCOUNT_SID="ACtest",
                       TWILIO_AUTH_TOKEN="token", TWILIO_WHATSAPP_FROM="whatsapp:+14155550100",
                       WHATSAPP_TEMPLATE_SID="HXtest", TWILIO_STATUS_CALLBACK_URL="")
    def test_resolution_creates_and_sends_opted_in_notification(self):
        contact = CustomerContact.objects.create(email="wa@example.com", whatsapp_number="+14155550123", whatsapp_consent=True)
        with patch("tickets.services.whatsapp_service.Client") as client_class:
            client_class.return_value.messages.create.return_value.sid = "SM123"
            with self.captureOnCommitCallbacks(execute=True):
                result = self.client.patch(f"/api/tickets/{self.ticket.pk}/", {"status": "resolved"}, format="json")
        self.assertEqual(result.status_code, 200)
        item = WhatsAppNotification.objects.get(ticket=self.ticket, customer=contact)
        self.assertEqual(item.status, "sent")
        self.assertEqual(item.twilio_message_sid, "SM123")

    def test_resolution_without_contact_or_consent_skips_whatsapp(self):
        self.client.patch(f"/api/tickets/{self.ticket.pk}/", {"status": "resolved"}, format="json")
        self.assertFalse(WhatsAppNotification.objects.exists())

    @override_settings(WHATSAPP_ENABLED=True, WHATSAPP_PROVIDER="twilio", TWILIO_ACCOUNT_SID="ACtest",
                       TWILIO_AUTH_TOKEN="token", TWILIO_WHATSAPP_FROM="whatsapp:+14155550100",
                       WHATSAPP_TEMPLATE_SID="HXtest")
    def test_missing_consent_and_disabled_provider_do_not_create_notification(self):
        CustomerContact.objects.create(email="wa@example.com", whatsapp_number="+14155550123", whatsapp_consent=False)
        self.client.patch(f"/api/tickets/{self.ticket.pk}/", {"status": "resolved"}, format="json")
        self.assertFalse(WhatsAppNotification.objects.exists())

    def test_sender_failure_is_sanitized(self):
        customer = CustomerContact.objects.create(email="wa@example.com", whatsapp_number="+14155550123", whatsapp_consent=True)
        item = WhatsAppNotification.objects.create(ticket=self.ticket, customer=customer, recipient_number="+14155550123")
        with patch("tickets.services.whatsapp_service.configuration_ready", return_value=True), patch("tickets.services.whatsapp_service.Client", side_effect=RuntimeError("private token data")):
            self.assertEqual(send_whatsapp_notification_task(item.pk), "failed")
        item.refresh_from_db()
        self.assertEqual(item.error_code, "network_error")
        self.assertNotIn("private", item.error_code)

    @override_settings(WHATSAPP_ENABLED=True, WHATSAPP_PROVIDER="twilio", TWILIO_ACCOUNT_SID="ACtest",
                       TWILIO_AUTH_TOKEN="token", TWILIO_WHATSAPP_FROM="whatsapp:+14155550100",
                       WHATSAPP_TEMPLATE_SID="HXtest")
    def test_twilio_rejection_preserves_documentation_error_code(self):
        item = WhatsAppNotification.objects.create(
            ticket=self.ticket,
            recipient_number="+14155550123",
        )
        twilio_error = TwilioRestException(
            status=422,
            uri="/Messages",
            msg="Sensitive provider details",
            code=63016,
        )
        with patch("tickets.services.whatsapp_service.Client") as client_class:
            client_class.return_value.messages.create.side_effect = twilio_error
            result = send_whatsapp_notification(item)

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "twilio_63016")
        self.assertEqual(result.error_detail, "Sensitive provider details")
        self.assertNotIn("Sensitive", result.error_code)

    @override_settings(WHATSAPP_ENABLED=True, WHATSAPP_PROVIDER="twilio", TWILIO_ACCOUNT_SID="ACtest",
                       TWILIO_AUTH_TOKEN="secret-token", TWILIO_WHATSAPP_FROM="whatsapp:+14155550100",
                       WHATSAPP_TEMPLATE_SID="HXtest")
    def test_twilio_error_detail_is_sanitized_and_saved_for_agent(self):
        customer = CustomerContact.objects.create(
            email="wa@example.com",
            whatsapp_number="+14155550123",
            whatsapp_consent=True,
        )
        item = WhatsAppNotification.objects.create(
            ticket=self.ticket,
            customer=customer,
            recipient_number="+14155550123",
        )
        twilio_error = TwilioRestException(
            status=422,
            uri="/Messages",
            msg="Rejected secret-token while sending to +14155550123 using TWILIO_ACCOUNT_SID_PLACEHOLDER",
            code=572002,
        )
        with patch("tickets.services.whatsapp_service.Client") as client_class:
            client_class.return_value.messages.create.side_effect = twilio_error
            self.assertEqual(send_whatsapp_notification_task(item.pk), "failed")

        item.refresh_from_db()
        self.assertEqual(item.error_code, "twilio_572002")
        self.assertNotIn("secret-token", item.error_detail)
        self.assertNotIn("+14155550123", item.error_detail)
        self.assertNotIn("TWILIO_ACCOUNT_SID_PLACEHOLDER", item.error_detail)
        response = self.client.get(f"/api/tickets/{self.ticket.pk}/whatsapp-notifications/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["notifications"][0]["error_detail"], item.error_detail)

    def test_whatsapp_contact_requires_valid_number_and_consent(self):
        bad = self.client.put(f"/api/tickets/{self.ticket.pk}/whatsapp-contact/", {"number": "555", "consent": True}, format="json")
        self.assertEqual(bad.status_code, 400)
        good = self.client.put(f"/api/tickets/{self.ticket.pk}/whatsapp-contact/", {"number": "+14155550123", "consent": True}, format="json")
        self.assertEqual(good.status_code, 200)
        self.assertEqual(good.data["number"], "+*******0123")

    def test_webhook_rejects_missing_signature(self):
        response = APIClient().post("/api/whatsapp/webhook/", {"MessageSid": "SM123", "MessageStatus": "delivered"})
        self.assertEqual(response.status_code, 403)

    def test_retry_requires_auth_and_respects_attempt_limit(self):
        item = WhatsAppNotification.objects.create(ticket=self.ticket, recipient_number="+14155550123", status="failed")
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(f"/api/tickets/{self.ticket.pk}/retry-whatsapp-notification/").status_code, 401)
        self.client.force_authenticate(self.agent)
        item.attempt_count = WhatsAppNotification.MAX_ATTEMPTS
        item.save(update_fields=["attempt_count"])
        self.assertEqual(self.client.post(f"/api/tickets/{self.ticket.pk}/retry-whatsapp-notification/").status_code, 409)

    def test_retry_limit_allows_confirmed_new_attempt_after_fix(self):
        item = WhatsAppNotification.objects.create(
            ticket=self.ticket,
            recipient_number="+14155550123",
            status="failed",
            attempt_count=WhatsAppNotification.MAX_ATTEMPTS,
            error_code="twilio_572002",
            error_detail="Template variables are invalid.",
        )
        with patch("tickets.views.enqueue_whatsapp_notification") as enqueue:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    f"/api/tickets/{self.ticket.pk}/retry-whatsapp-notification/",
                    {"notification_id": item.pk, "retry_after_fix": True},
                    format="json",
                )

        self.assertEqual(response.status_code, 202)
        item.refresh_from_db()
        self.assertEqual(item.status, "pending")
        self.assertEqual(item.attempt_count, 0)
        self.assertEqual(item.error_code, "")
        self.assertEqual(item.error_detail, "")
        enqueue.assert_called_once_with(item.pk)

    def test_retry_targets_selected_failed_notification_when_newer_message_is_sent(self):
        failed = WhatsAppNotification.objects.create(
            ticket=self.ticket,
            recipient_number="+14155550123",
            status="failed",
            error_code="provider_rejected",
        )
        WhatsAppNotification.objects.create(
            ticket=self.ticket,
            recipient_number="+14155550123",
            status="sent",
        )

        with patch("tickets.views.enqueue_whatsapp_notification") as enqueue:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    f"/api/tickets/{self.ticket.pk}/retry-whatsapp-notification/",
                    {"notification_id": failed.pk},
                    format="json",
                )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["notification_id"], failed.pk)
        failed.refresh_from_db()
        self.assertEqual(failed.status, "pending")
        enqueue.assert_called_once_with(failed.pk)

    def test_retry_without_id_ignores_newer_nonfailed_notifications(self):
        failed = WhatsAppNotification.objects.create(
            ticket=self.ticket,
            recipient_number="+14155550123",
            status="failed",
        )
        WhatsAppNotification.objects.create(
            ticket=self.ticket,
            recipient_number="+14155550123",
            status="sent",
        )
        with patch("tickets.views.enqueue_whatsapp_notification") as enqueue:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    f"/api/tickets/{self.ticket.pk}/retry-whatsapp-notification/"
                )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["notification_id"], failed.pk)
        failed.refresh_from_db()
        self.assertEqual(failed.status, "pending")
        enqueue.assert_called_once_with(failed.pk)

    def test_retry_reports_when_selected_notification_is_already_sent(self):
        sent = WhatsAppNotification.objects.create(
            ticket=self.ticket,
            recipient_number="+14155550123",
            status="sent",
        )
        response = self.client.post(
            f"/api/tickets/{self.ticket.pk}/retry-whatsapp-notification/",
            {"notification_id": sent.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("is sent", response.data["detail"])

    def test_rollback_does_not_create_or_dispatch_whatsapp(self):
        customer = CustomerContact.objects.create(email="wa@example.com", whatsapp_number="+14155550123", whatsapp_consent=True)
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            try:
                from django.db import transaction
                with transaction.atomic():
                    item = WhatsAppNotification.objects.create(ticket=self.ticket, customer=customer, recipient_number=customer.whatsapp_number)
                    transaction.on_commit(lambda: send_whatsapp_notification_task(item.pk))
                    raise RuntimeError("rollback")
            except RuntimeError:
                pass
        self.assertEqual(callbacks, [])
        self.assertFalse(WhatsAppNotification.objects.exists())

    @override_settings(TWILIO_AUTH_TOKEN="test-token")
    def test_signed_delivery_callbacks_are_idempotent_and_never_regress(self):
        from twilio.request_validator import RequestValidator
        contact = CustomerContact.objects.create(email="wa@example.com", whatsapp_number="+14155550123", whatsapp_consent=True)
        item = WhatsAppNotification.objects.create(ticket=self.ticket, customer=contact, recipient_number="+14155550123",
                                                    twilio_message_sid="SM123", status="sent")
        url = "http://testserver/api/whatsapp/webhook/"
        validator = RequestValidator("test-token")
        data = {"MessageSid": "SM123", "MessageStatus": "delivered"}
        signature = validator.compute_signature(url, data)
        response = APIClient().post("/api/whatsapp/webhook/", data, HTTP_X_TWILIO_SIGNATURE=signature)
        self.assertEqual(response.status_code, 204)
        item.refresh_from_db()
        first_delivery_time = item.delivered_at
        self.assertEqual(item.status, "delivered")
        response = APIClient().post("/api/whatsapp/webhook/", data, HTTP_X_TWILIO_SIGNATURE=signature)
        self.assertEqual(response.status_code, 204)
        stale = {"MessageSid": "SM123", "MessageStatus": "sent"}
        stale_signature = validator.compute_signature(url, stale)
        APIClient().post("/api/whatsapp/webhook/", stale, HTTP_X_TWILIO_SIGNATURE=stale_signature)
        item.refresh_from_db()
        self.assertEqual(item.status, "delivered")
        self.assertEqual(item.delivered_at, first_delivery_time)
