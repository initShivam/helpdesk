from io import StringIO
from unittest.mock import Mock, patch

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from .services import (
    get_state_instance,
    normalize_phone_number,
    send_whatsapp_message,
    validate_configuration,
)
from .tasks import send_whatsapp_message_task


GREEN_SETTINGS = {
    "GREEN_API_URL": "https://api.green-api.example",
    "GREEN_API_MEDIA_URL": "https://media.green-api.example",
    "GREEN_API_INSTANCE_ID": "instance-test",
    "GREEN_API_TOKEN": "secret-test-token",
    "GREEN_API_TIMEOUT_SECONDS": 7,
}


@override_settings(**GREEN_SETTINGS)
class GreenApiServiceTests(SimpleTestCase):
    def test_configuration_validation_does_not_return_secret_values(self):
        self.assertEqual(validate_configuration(), ())

    @override_settings(GREEN_API_TOKEN="")
    def test_missing_configuration_names_are_reported_without_values(self):
        self.assertEqual(validate_configuration(), ("GREEN_API_TOKEN",))

    @override_settings(GREEN_API_URL="https://user:password@api.example/path?token=secret")
    def test_configuration_rejects_urls_containing_embedded_credentials(self):
        self.assertIn("GREEN_API_URL_invalid", validate_configuration())

    def test_normalizes_supported_indian_mobile_formats(self):
        self.assertEqual(normalize_phone_number("9876543210"), "919876543210")
        self.assertEqual(normalize_phone_number("09876543210"), "919876543210")
        self.assertEqual(normalize_phone_number("+91 98765-43210"), "919876543210")
        self.assertEqual(normalize_phone_number("919876543210"), "919876543210")

    def test_rejects_invalid_phone_numbers(self):
        with self.assertRaisesRegex(ValueError, "invalid_indian_phone_number"):
            normalize_phone_number("+14155550123")
        with self.assertRaisesRegex(ValueError, "invalid_indian_phone_number"):
            normalize_phone_number("12345")

    @patch("whatsapp.services.requests.get")
    def test_get_state_instance_authorized(self, get):
        get.return_value = Mock(ok=True, json=lambda: {"stateInstance": "authorized"})

        result = get_state_instance()

        self.assertEqual(result.status, "authorized")
        args, kwargs = get.call_args
        self.assertEqual(
            args[0],
            "https://api.green-api.example/waInstanceinstance-test/"
            "getStateInstance/secret-test-token",
        )
        self.assertEqual(kwargs["timeout"], 7)

    @patch("whatsapp.services.requests.get")
    def test_get_state_instance_not_authorized(self, get):
        get.return_value = Mock(ok=True, json=lambda: {"stateInstance": "notAuthorized"})

        self.assertEqual(get_state_instance().status, "notAuthorized")

    @patch("whatsapp.services.requests.get")
    def test_get_state_instance_http_error_is_safe(self, get):
        get.return_value = Mock(ok=False, status_code=503)

        result = get_state_instance()

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error_code, "http_503")

    @patch("whatsapp.services.requests.get", side_effect=requests.RequestException(
        "request failed for https://api.example/secret-test-token"
    ))
    def test_request_logging_does_not_include_secret_token(self, get):
        with self.assertLogs("whatsapp.services", level="WARNING") as captured:
            result = get_state_instance()

        self.assertEqual(result.status, "error")
        self.assertNotIn("secret-test-token", "\n".join(captured.output))

    @patch("whatsapp.services.requests.post")
    def test_send_message_posts_required_chat_id_and_returns_provider_id(self, post):
        post.return_value = Mock(ok=True, json=lambda: {"idMessage": "provider-message-1"})

        result = send_whatsapp_message("(987) 654-3210", "Test message")

        self.assertEqual(result.status, "sent")
        self.assertEqual(result.message_id, "provider-message-1")
        args, kwargs = post.call_args
        self.assertEqual(
            args[0],
            "https://api.green-api.example/waInstanceinstance-test/"
            "sendMessage/secret-test-token",
        )
        self.assertEqual(kwargs["timeout"], 7)
        self.assertEqual(
            kwargs["json"],
            {"chatId": "919876543210@c.us", "message": "Test message"},
        )

    @patch("whatsapp.services.requests.post")
    def test_send_http_error_does_not_include_provider_response(self, post):
        post.return_value = Mock(ok=False, status_code=401, text="secret-test-token")

        result = send_whatsapp_message("9876543210", "Test message")

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error_code, "http_401")
        self.assertNotIn("secret-test-token", result.error_code)

    @patch("whatsapp.services.requests.post")
    def test_send_rejects_invalid_phone_or_message_without_request(self, post):
        invalid_phone = send_whatsapp_message("+14155550123", "Test")
        empty_message = send_whatsapp_message("9876543210", " ")

        self.assertEqual(invalid_phone.error_code, "invalid_indian_phone_number")
        self.assertEqual(empty_message.error_code, "invalid_message")
        post.assert_not_called()

    @patch("whatsapp.services.requests.post")
    @patch("whatsapp.services.requests.get")
    def test_celery_task_checks_authorization_before_sending(self, get, post):
        get.return_value = Mock(ok=True, json=lambda: {"stateInstance": "notAuthorized"})

        result = send_whatsapp_message_task.run("9876543210", "Test")

        self.assertEqual(result["status"], "notAuthorized")
        post.assert_not_called()

    @patch("whatsapp.services.requests.post")
    @patch("whatsapp.services.requests.get")
    def test_celery_task_sends_after_authorization(self, get, post):
        get.return_value = Mock(ok=True, json=lambda: {"stateInstance": "authorized"})
        post.return_value = Mock(ok=True, json=lambda: {"idMessage": "provider-message-2"})

        result = send_whatsapp_message_task.run("9876543210", "Test")

        self.assertEqual(result, {
            "status": "sent",
            "message_id": "provider-message-2",
            "error_code": "",
        })
        get.assert_called_once()
        post.assert_called_once()

    @patch("whatsapp.services.requests.post")
    @patch("whatsapp.services.requests.get")
    def test_test_command_checks_state_without_sending_by_default(self, get, post):
        get.return_value = Mock(ok=True, json=lambda: {"stateInstance": "authorized"})

        output = StringIO()
        call_command("send_whatsapp_test", stdout=output)

        self.assertIn("GREEN-API instance status: authorized", output.getvalue())
        post.assert_not_called()

    @override_settings(GREEN_API_TOKEN="")
    @patch("whatsapp.services.requests.post")
    @patch("whatsapp.services.requests.get")
    def test_test_command_reports_missing_settings_without_provider_request(self, get, post):
        with self.assertRaisesRegex(CommandError, "GREEN_API_TOKEN"):
            call_command("send_whatsapp_test", stdout=StringIO())

        get.assert_not_called()
        post.assert_not_called()

    @patch("whatsapp.services.requests.post")
    @patch("whatsapp.services.requests.get")
    def test_test_command_requires_explicit_send_confirmation(self, get, post):
        get.return_value = Mock(ok=True, json=lambda: {"stateInstance": "authorized"})

        with self.assertRaises(CommandError):
            call_command(
                "send_whatsapp_test",
                phone="9876543210",
                message="Test message",
                stdout=StringIO(),
            )

        post.assert_not_called()

    @patch("whatsapp.services.requests.post")
    @patch("whatsapp.services.requests.get")
    def test_test_command_sends_only_with_explicit_confirmation(self, get, post):
        get.return_value = Mock(ok=True, json=lambda: {"stateInstance": "authorized"})
        post.return_value = Mock(ok=True, json=lambda: {"idMessage": "provider-message-3"})

        call_command(
            "send_whatsapp_test",
            phone="9876543210",
            message="Test message",
            confirm_send=True,
            stdout=Mock(),
        )

        post.assert_called_once()
