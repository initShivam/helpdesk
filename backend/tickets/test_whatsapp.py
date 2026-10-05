import hashlib
import hmac
import json
from unittest.mock import Mock, patch

import requests

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from tickets.models import CustomerContact, Ticket, WhatsAppNotification
from tickets.services.whatsapp_service import normalize_whatsapp_number, send_whatsapp_notification
from tickets.tasks import send_whatsapp_notification_task


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="support@example.com",
    EMAIL_HOST_USER="support@example.com",
    EMAIL_HOST_PASSWORD="test",
    WHATSAPP_ENABLED=True,
    WHATSAPP_PROVIDER="meta",
    META_WHATSAPP_ACCESS_TOKEN="test-access-token",
    META_WHATSAPP_PHONE_NUMBER_ID="123456789012345",
    META_WHATSAPP_BUSINESS_ACCOUNT_ID="123456789012345",
    META_WHATSAPP_TEMPLATE_NAME="hello_world",
    META_WHATSAPP_TEMPLATE_LANGUAGE="en_US",
    META_WHATSAPP_VERIFY_TOKEN="test-verify-token",
    META_WHATSAPP_APP_SECRET="test-app-secret",
)
class WhatsAppIntegrationTests(TestCase):
    def setUp(self):
        self.agent = User.objects.create_user(username="wa-agent", password="test-password", role="AGENT")
        self.client = APIClient()
        self.client.force_authenticate(self.agent)
        self.ticket = Ticket.objects.create(
            ticket_number="WA-100",
            subject="Account help",
            requester_email="wa@example.com",
        )

    @staticmethod
    def mock_successful_meta_response(post_mock):
        post_mock.return_value.ok = True
        post_mock.return_value.status_code = 200
        post_mock.return_value.json.return_value = {
            "messages": [{"id": "wamid.test-message-id"}],
        }

    def test_phone_normalization(self):
        self.assertEqual(normalize_whatsapp_number(" +1 (415) 555-0123 "), "+14155550123")
        with self.assertRaises(ValueError):
            normalize_whatsapp_number("4155550123")

    def test_resolution_creates_and_sends_opted_in_notification(self):
        contact = CustomerContact.objects.create(
            email="wa@example.com",
            whatsapp_number="+14155550123",
            whatsapp_consent=True,
        )
        with patch("tickets.services.whatsapp_service.requests.post") as post_mock:
            self.mock_successful_meta_response(post_mock)
            with self.captureOnCommitCallbacks(execute=True):
                result = self.client.patch(
                    f"/api/tickets/{self.ticket.pk}/",
                    {"status": "resolved"},
                    format="json",
                )
        self.assertEqual(result.status_code, 200)
        item = WhatsAppNotification.objects.get(ticket=self.ticket, customer=contact)
        self.assertEqual(item.status, "sent")
        self.assertEqual(item.meta_message_id, "wamid.test-message-id")
        url = post_mock.call_args.args[0]
        self.assertEqual(url, "https://graph.facebook.com/v25.0/123456789012345/messages")
        self.assertEqual(
            post_mock.call_args.kwargs["headers"],
            {
                "Authorization": "Bearer test-access-token",
                "Content-Type": "application/json",
            },
        )
        payload = post_mock.call_args.kwargs["json"]
        self.assertEqual(payload["messaging_product"], "whatsapp")
        self.assertEqual(payload["to"], "14155550123")
        self.assertEqual(
            payload["template"],
            {"name": "hello_world", "language": {"code": "en_US"}},
        )

    def test_send_uses_current_customer_number_instead_of_stale_notification_number(self):
        customer = CustomerContact.objects.create(
            email="wa@example.com",
            whatsapp_number="+14155550123",
            whatsapp_consent=True,
        )
        item = WhatsAppNotification.objects.create(
            ticket=self.ticket,
            customer=customer,
            recipient_number="+14155556079",
        )
        customer.whatsapp_number = "+14155550124"
        customer.save(update_fields=["whatsapp_number"])

        with patch("tickets.services.whatsapp_service.requests.post") as post_mock:
            self.mock_successful_meta_response(post_mock)
            self.assertEqual(send_whatsapp_notification_task(item.pk), "sent")

        item.refresh_from_db()
        self.assertEqual(item.recipient_number, "+14155550124")
        payload = post_mock.call_args.kwargs["json"]
        self.assertEqual(payload["to"], "14155550124")

    def test_resolution_without_contact_or_consent_skips_whatsapp(self):
        self.client.patch(f"/api/tickets/{self.ticket.pk}/", {"status": "resolved"}, format="json")
        self.assertFalse(WhatsAppNotification.objects.exists())

    def test_sender_failure_is_sanitized(self):
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
        with patch(
            "tickets.services.whatsapp_service.requests.post",
            side_effect=requests.ConnectionError("private test-access-token"),
        ):
            self.assertEqual(send_whatsapp_notification_task(item.pk), "failed")
        item.refresh_from_db()
        self.assertEqual(item.error_code, "network_error")
        self.assertNotIn("private", item.error_code)

    def test_meta_rejection_stores_safe_provider_code_and_detail(self):
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
        provider_error = {
            "error": {
                "code": 132001,
                "message": "Template rejected for +14155550123 with test-access-token",
            }
        }
        failure = Mock(ok=False, status_code=400)
        failure.json.return_value = provider_error
        with patch("tickets.services.whatsapp_service.requests.post", return_value=failure):
            result = send_whatsapp_notification(item)

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "meta_132001")
        self.assertNotIn("test-access-token", result.error_detail)
        self.assertNotIn("+14155550123", result.error_detail)
        with patch("tickets.services.whatsapp_service.requests.post", return_value=failure):
            self.assertEqual(send_whatsapp_notification_task(item.pk), "failed")
        item.refresh_from_db()
        self.assertEqual(item.error_code, "meta_132001")
        response = self.client.get(f"/api/tickets/{self.ticket.pk}/whatsapp-notifications/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["notifications"][0]["error_detail"], item.error_detail)

    def test_meta_rate_limit_is_transient(self):
        provider_error = {"error": {"code": 4, "message": "Temporarily rate limited", "is_transient": True}}
        failure = Mock(ok=False, status_code=400)
        failure.json.return_value = provider_error
        item = WhatsAppNotification.objects.create(ticket=self.ticket, recipient_number="+14155550123")
        with patch("tickets.services.whatsapp_service.requests.post", return_value=failure):
            result = send_whatsapp_notification(item)
        self.assertFalse(result.success)
        self.assertTrue(result.transient)
        self.assertEqual(result.error_code, "provider_unavailable")

    @override_settings(META_WHATSAPP_ACCESS_TOKEN='  "test-access-token"  ')
    def test_authorization_header_strips_accidental_outer_quotes(self):
        item = WhatsAppNotification.objects.create(ticket=self.ticket, recipient_number="+14155550123")
        with patch("tickets.services.whatsapp_service.requests.post") as post_mock:
            self.mock_successful_meta_response(post_mock)
            result = send_whatsapp_notification(item)
        self.assertTrue(result.success)
        self.assertEqual(
            post_mock.call_args.kwargs["headers"]["Authorization"],
            "Bearer test-access-token",
        )

    def test_whatsapp_contact_requires_valid_number_and_consent(self):
        bad = self.client.put(
            f"/api/tickets/{self.ticket.pk}/whatsapp-contact/",
            {"number": "555", "consent": True},
            format="json",
        )
        self.assertEqual(bad.status_code, 400)
        good = self.client.put(
            f"/api/tickets/{self.ticket.pk}/whatsapp-contact/",
            {"number": "+14155550123", "consent": True},
            format="json",
        )
        self.assertEqual(good.status_code, 200)
        self.assertEqual(good.data["number"], "+*******0123")

    def test_webhook_verification_requires_matching_token(self):
        client = APIClient()
        rejected = client.get("/api/whatsapp/webhook/", {
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong",
            "hub.challenge": "challenge",
        })
        self.assertEqual(rejected.status_code, 403)
        accepted = client.get("/api/whatsapp/webhook/", {
            "hub.mode": "subscribe",
            "hub.verify_token": "test-verify-token",
            "hub.challenge": "challenge",
        })
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.content, b"challenge")

    def test_webhook_rejects_missing_or_invalid_signature(self):
        client = APIClient()
        body = json.dumps({"entry": []})
        missing = client.post("/api/whatsapp/webhook/", body, content_type="application/json")
        self.assertEqual(missing.status_code, 403)
        invalid = client.post(
            "/api/whatsapp/webhook/",
            body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256="sha256=invalid",
        )
        self.assertEqual(invalid.status_code, 403)

    def test_signed_status_callbacks_are_idempotent_and_never_regress(self):
        item = WhatsAppNotification.objects.create(
            ticket=self.ticket,
            recipient_number="+14155550123",
            meta_message_id="wamid.test-message-id",
            status="sent",
        )
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "statuses": [{
                            "id": "wamid.test-message-id",
                            "status": "delivered",
                            "timestamp": "1791191400",
                            "recipient_id": "14155550123",
                        }],
                    },
                }],
            }],
        }
        body = json.dumps(payload).encode("utf-8")
        signature = hmac.new(b"test-app-secret", body, hashlib.sha256).hexdigest()
        client = APIClient()
        response = client.post(
            "/api/whatsapp/webhook/",
            body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=f"sha256={signature}",
        )
        self.assertEqual(response.status_code, 204)
        item.refresh_from_db()
        first_delivery_time = item.delivered_at
        self.assertEqual(item.status, "delivered")
        duplicate = client.post(
            "/api/whatsapp/webhook/",
            body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=f"sha256={signature}",
        )
        self.assertEqual(duplicate.status_code, 204)
        stale_payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "statuses": [{
                            "id": "wamid.test-message-id",
                            "status": "sent",
                        }],
                    },
                }],
            }],
        }
        stale_body = json.dumps(stale_payload).encode("utf-8")
        stale_signature = hmac.new(b"test-app-secret", stale_body, hashlib.sha256).hexdigest()
        client.post(
            "/api/whatsapp/webhook/",
            stale_body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=f"sha256={stale_signature}",
        )
        item.refresh_from_db()
        self.assertEqual(item.status, "delivered")
        self.assertEqual(item.delivered_at, first_delivery_time)

    def test_retry_requires_auth_and_respects_attempt_limit(self):
        item = WhatsAppNotification.objects.create(
            ticket=self.ticket,
            recipient_number="+14155550123",
            status="failed",
        )
        self.client.force_authenticate(None)
        self.assertEqual(
            self.client.post(f"/api/tickets/{self.ticket.pk}/retry-whatsapp-notification/").status_code,
            401,
        )
        self.client.force_authenticate(self.agent)
        item.attempt_count = WhatsAppNotification.MAX_ATTEMPTS
        item.save(update_fields=["attempt_count"])
        self.assertEqual(
            self.client.post(f"/api/tickets/{self.ticket.pk}/retry-whatsapp-notification/").status_code,
            409,
        )

    def test_retry_limit_allows_confirmed_new_attempt_after_fix(self):
        item = WhatsAppNotification.objects.create(
            ticket=self.ticket,
            recipient_number="+14155550123",
            status="failed",
            attempt_count=WhatsAppNotification.MAX_ATTEMPTS,
            error_code="meta_132001",
            error_detail="Template configuration is invalid.",
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

    def test_retry_after_contact_change_uses_current_opted_in_number(self):
        contact = CustomerContact.objects.create(
            email="wa@example.com",
            whatsapp_number="+14155550123",
            whatsapp_consent=True,
        )
        item = WhatsAppNotification.objects.create(
            ticket=self.ticket,
            customer=contact,
            recipient_number="+14155556079",
            status="failed",
            error_code="contact_changed",
        )
        with patch("tickets.views.enqueue_whatsapp_notification") as enqueue:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    f"/api/tickets/{self.ticket.pk}/retry-whatsapp-notification/",
                    {"notification_id": item.pk},
                    format="json",
                )
        self.assertEqual(response.status_code, 202)
        item.refresh_from_db()
        self.assertEqual(item.recipient_number, "+14155550123")
        self.assertEqual(item.status, "pending")
        enqueue.assert_called_once_with(item.pk)

    def test_retry_after_contact_change_requires_current_consent(self):
        contact = CustomerContact.objects.create(
            email="wa@example.com",
            whatsapp_number="+14155550123",
            whatsapp_consent=False,
        )
        item = WhatsAppNotification.objects.create(
            ticket=self.ticket,
            customer=contact,
            recipient_number="+14155556079",
            status="failed",
            error_code="contact_changed",
        )
        response = self.client.post(
            f"/api/tickets/{self.ticket.pk}/retry-whatsapp-notification/",
            {"notification_id": item.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 409)

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
        customer = CustomerContact.objects.create(
            email="wa@example.com",
            whatsapp_number="+14155550123",
            whatsapp_consent=True,
        )
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            try:
                from django.db import transaction

                with transaction.atomic():
                    item = WhatsAppNotification.objects.create(
                        ticket=self.ticket,
                        customer=customer,
                        recipient_number=customer.whatsapp_number,
                    )
                    transaction.on_commit(lambda: send_whatsapp_notification_task(item.pk))
                    raise RuntimeError("rollback")
            except RuntimeError:
                pass
        self.assertEqual(callbacks, [])
        self.assertFalse(WhatsAppNotification.objects.exists())
