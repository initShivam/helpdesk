import json
from email.message import EmailMessage

from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from unittest.mock import patch

from .auto_resolution import (
    find_similar_resolutions,
    response_requires_manual_review,
    ticket_requires_manual_review,
)
from .models import (
    AutoResolutionAudit,
    AutoResolutionSettings,
    CustomerContact,
    ResolvedTicketKnowledge,
    Ticket,
    TicketMessage,
)
from .tasks import (
    process_auto_resolution,
    send_auto_resolution_email_task,
    send_auto_resolution_whatsapp_task,
)


class AutoResolutionTests(TestCase):
    def setUp(self):
        self.auto_settings, _ = AutoResolutionSettings.objects.get_or_create(pk=1)
        self.auto_settings.enabled = True
        self.auto_settings.email_auto_reply = True
        self.auto_settings.whatsapp_auto_reply = False
        self.auto_settings.simulation_mode = True
        self.auto_settings.minimum_threshold = 0.85
        self.auto_settings.save()

    def make_ticket(
        self,
        *,
        subject="Printer cannot connect",
        body="The printer is offline.",
        status="open",
        category="general",
        priority="medium",
        source="email",
    ):
        ticket = Ticket.objects.create(
            ticket_number=f"AUTO-{Ticket.objects.count() + 1}",
            subject=subject,
            description=body,
            requester_email="customer@example.com",
            status=status,
            category=category,
            priority=priority,
            ai_category_confidence=0.9,
            source=source,
        )
        TicketMessage.objects.create(
            ticket=ticket,
            body=body,
            message_type="customer",
        )
        return ticket

    def add_human_resolution(self, ticket, response="Restart the printer and reconnect it to the network."):
        return TicketMessage.objects.create(
            ticket=ticket,
            body=response,
            message_type="agent",
            is_ai_generated=False,
            is_draft=False,
        )

    def add_whatsapp_contact(self, ticket):
        return CustomerContact.objects.create(
            email=ticket.requester_email,
            whatsapp_number="+919876543210",
            whatsapp_consent=True,
        )

    @patch("tickets.auto_resolution.embed_text", return_value=([1.0, 0.0], "test-model"))
    def test_retrieval_uses_only_resolved_tickets_with_human_agent_responses(self, embed_text):
        resolved = self.make_ticket(status="resolved")
        self.add_human_resolution(resolved)
        resolved_without_human_answer = self.make_ticket(status="resolved")
        TicketMessage.objects.create(
            ticket=resolved_without_human_answer,
            body="Generated draft only",
            message_type="agent",
            is_ai_generated=True,
            is_draft=False,
        )
        open_ticket = self.make_ticket(status="open")
        self.add_human_resolution(open_ticket)
        new_ticket = self.make_ticket()

        matches = find_similar_resolutions(new_ticket)

        self.assertEqual([match.ticket_id for match in matches], [resolved.id])
        self.assertEqual(matches[0].score, 1.0)
        self.assertTrue(ResolvedTicketKnowledge.objects.filter(ticket=resolved).exists())
        self.assertEqual(embed_text.call_count, 2)

    @patch("tickets.auto_resolution.embed_text", return_value=([1.0, 0.0], "test-model"))
    def test_retrieval_ignores_short_or_generic_human_resolutions(self, embed_text):
        resolved = self.make_ticket(status="resolved")
        self.add_human_resolution(resolved, "Thanks.")
        new_ticket = self.make_ticket()

        self.assertEqual(find_similar_resolutions(new_ticket), [])

    def test_risk_and_unsupported_claims_require_agent_review(self):
        refund_ticket = self.make_ticket(
            subject="Refund request",
            body="Please refund this charge.",
            category="refund",
        )
        urgent_ticket = self.make_ticket(
            subject="Urgent outage",
            body="The system is down immediately.",
            priority="high",
        )
        routine_ticket = self.make_ticket()

        self.assertEqual(ticket_requires_manual_review(refund_ticket), "sensitive_category")
        self.assertEqual(ticket_requires_manual_review(urgent_ticket), "high_priority")
        self.assertEqual(ticket_requires_manual_review(routine_ticket), "")
        self.assertTrue(response_requires_manual_review("We have processed your refund."))
        self.assertTrue(response_requires_manual_review("You will receive the refund within 3 days."))
        self.assertFalse(response_requires_manual_review("Please restart the printer and let us know if it reconnects."))

    def test_missing_or_uncertain_classification_requires_agent_review(self):
        ticket = self.make_ticket()
        ticket.ai_category_confidence = None
        self.assertEqual(ticket_requires_manual_review(ticket), "classification_uncertain")

        ticket.ai_category_confidence = 0.5
        self.assertEqual(ticket_requires_manual_review(ticket), "classification_uncertain")

    @patch(
        "tickets.auto_resolution.find_similar_resolutions",
        return_value=[
            type("Match", (), {
                "ticket_id": 99,
                "problem": "Printer offline",
                "resolution": "Restart the printer and reconnect it.",
                "score": 0.94,
            })()
        ],
    )
    @patch(
        "tickets.auto_resolution.generate_with_openai",
        return_value=(
            json.dumps({
                "response": "Please restart the printer and reconnect it to the network.",
                "confidence": 0.93,
                "needs_review": False,
            }),
            {},
        ),
    )
    def test_simulation_creates_audited_agent_draft_without_sending(self, generate, matches):
        ticket = self.make_ticket()

        audit_id = process_auto_resolution.run(ticket.pk)

        audit = AutoResolutionAudit.objects.get(pk=audit_id)
        self.assertEqual(audit.decision, "simulation")
        self.assertEqual(audit.decision_reason, "simulation_mode")
        self.assertEqual(audit.send_status, "not_sent")
        self.assertEqual(audit.matched_ticket_ids, [99])
        self.assertEqual(audit.similarity_score, 0.94)
        self.assertEqual(audit.ai_confidence, 0.93)
        self.assertEqual(audit.generated_response, "Please restart the printer and reconnect it to the network.")
        draft = TicketMessage.objects.get(ticket=ticket, is_draft=True)
        self.assertTrue(draft.is_ai_generated)
        self.assertEqual(draft.ai_log.operation, "auto_resolution")

    @patch(
        "tickets.auto_resolution.find_similar_resolutions",
        return_value=[
            type("Match", (), {
                "ticket_id": 99,
                "problem": "Printer offline",
                "resolution": "Restart the printer.",
                "score": 0.5,
            })()
        ],
    )
    @patch(
        "tickets.auto_resolution.generate_with_openai",
        return_value=(
            json.dumps({
                "response": "Please allow our team to review this issue.",
                "confidence": 0.95,
                "needs_review": False,
            }),
            {},
        ),
    )
    def test_low_similarity_is_kept_in_agent_review(self, generate, matches):
        ticket = self.make_ticket()

        audit_id = process_auto_resolution.run(ticket.pk)

        audit = AutoResolutionAudit.objects.get(pk=audit_id)
        self.assertEqual(audit.decision, "agent_review")
        self.assertEqual(audit.decision_reason, "similarity_below_threshold")
        self.assertEqual(audit.send_status, "not_sent")
        self.assertTrue(TicketMessage.objects.filter(ticket=ticket, is_draft=True).exists())

    @patch(
        "tickets.auto_resolution.find_similar_resolutions",
        return_value=[
            type("Match", (), {
                "ticket_id": 99,
                "problem": "Printer offline",
                "resolution": "Restart the printer and reconnect it.",
                "score": 0.96,
            })()
        ],
    )
    @patch(
        "tickets.auto_resolution.generate_with_openai",
        return_value=(
            json.dumps({
                "response": "Please restart the printer and reconnect it to the network.",
                "confidence": 0.7,
                "needs_review": False,
            }),
            {},
        ),
    )
    def test_low_ai_confidence_is_kept_in_agent_review(self, generate, matches):
        ticket = self.make_ticket()

        audit_id = process_auto_resolution.run(ticket.pk)

        audit = AutoResolutionAudit.objects.get(pk=audit_id)
        self.assertEqual(audit.decision, "agent_review")
        self.assertEqual(audit.decision_reason, "confidence_below_threshold")
        self.assertEqual(audit.send_status, "not_sent")

    @patch("tickets.auto_resolution.generate_with_openai")
    @patch("tickets.auto_resolution.find_similar_resolutions")
    def test_sensitive_tickets_are_not_sent_to_the_llm(self, find_matches, generate):
        ticket = self.make_ticket(
            subject="Refund request",
            body="Please refund this payment.",
            category="refund",
        )

        audit_id = process_auto_resolution.run(ticket.pk)

        audit = AutoResolutionAudit.objects.get(pk=audit_id)
        self.assertEqual(audit.decision, "agent_review")
        self.assertEqual(audit.decision_reason, "sensitive_category")
        find_matches.assert_not_called()
        generate.assert_not_called()

    @patch("email_ingestion.tasks.enqueue_auto_resolution")
    def test_newly_received_email_enqueues_auto_resolution_after_commit(self, enqueue):
        from email_ingestion.parser import parse_email
        from email_ingestion.tasks import persist_email

        message = EmailMessage()
        message["From"] = "Customer <customer@example.com>"
        message["To"] = "support@example.com"
        message["Subject"] = "Printer issue"
        message["Message-ID"] = "<auto-resolution@example.com>"
        message.set_content("The printer is not working.")

        with self.captureOnCommitCallbacks(execute=True):
            inbound, created = persist_email(parse_email(message.as_bytes()))

        self.assertTrue(created)
        enqueue.assert_called_once_with(inbound.ticket_id)

    @override_settings(
        CELERY_TASK_ALWAYS_EAGER=True,
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="support@example.com",
    )
    @patch(
        "tickets.auto_resolution.find_similar_resolutions",
        return_value=[
            type("Match", (), {
                "ticket_id": 99,
                "problem": "Printer offline",
                "resolution": "Restart the printer.",
                "score": 0.94,
            })()
        ],
    )
    @patch(
        "tickets.auto_resolution.generate_with_openai",
        return_value=(
            json.dumps({
                "response": "Please restart the printer and reconnect it.",
                "confidence": 0.93,
                "needs_review": True,
            }),
            {},
        ),
    )
    def test_high_confidence_auto_send_ignores_model_review_flag(self, generate, matches):
        self.auto_settings.simulation_mode = False
        self.auto_settings.save()
        ticket = self.make_ticket()

        audit_id = process_auto_resolution.run(ticket.pk)

        audit = AutoResolutionAudit.objects.get(pk=audit_id)
        self.assertEqual(audit.decision, "auto_sent")
        self.assertEqual(audit.send_status, "sent")
        self.assertEqual(audit.channel, "email")
        self.assertEqual(audit.selected_match_id, 99)
        self.assertEqual(audit.provider_result, "accepted_by_email_backend")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [ticket.requester_email])
        self.assertEqual(mail.outbox[0].body, audit.generated_response)
        self.assertTrue(
            TicketMessage.objects.filter(
                ticket=ticket,
                ai_log=audit.ai_log,
                is_draft=False,
            ).exists()
        )
        self.assertEqual(send_auto_resolution_email_task.run(audit.pk), "sent")
        self.assertEqual(len(mail.outbox), 1)

    @patch("tickets.auto_resolution.find_similar_resolutions", return_value=[])
    @patch("tickets.auto_resolution.generate_with_openai")
    def test_no_resolved_match_is_reviewed_without_generation(self, generate, matches):
        ticket = self.make_ticket()

        audit_id = process_auto_resolution.run(ticket.pk)

        audit = AutoResolutionAudit.objects.get(pk=audit_id)
        self.assertEqual(audit.decision_reason, "no_similar_resolved_case")
        self.assertEqual(audit.channel, "email")
        self.assertEqual(audit.matched_ticket_ids, [])
        generate.assert_not_called()

    @patch("tickets.auto_resolution.find_similar_resolutions")
    @patch("tickets.auto_resolution.generate_with_openai")
    def test_disabled_email_channel_does_not_generate_or_send(self, generate, matches):
        self.auto_settings.email_auto_reply = False
        self.auto_settings.save()
        ticket = self.make_ticket()

        audit_id = process_auto_resolution.run(ticket.pk)

        audit = AutoResolutionAudit.objects.get(pk=audit_id)
        self.assertEqual(audit.decision_reason, "email_auto_reply_disabled")
        self.assertEqual(audit.channel, "email")
        matches.assert_not_called()
        generate.assert_not_called()

    @override_settings(WHATSAPP_PROVIDER="meta")
    @override_settings(
        CELERY_TASK_ALWAYS_EAGER=True,
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="support@example.com",
    )
    @patch(
        "tickets.auto_resolution.find_similar_resolutions",
        return_value=[
            type("Match", (), {
                "ticket_id": 99,
                "problem": "Printer offline",
                "resolution": "Restart the printer and reconnect it.",
                "score": 0.94,
            })()
        ],
    )
    @patch(
        "tickets.auto_resolution.generate_with_openai",
        return_value=(
            json.dumps({
                "response": "Please restart the printer and reconnect it to the network.",
                "confidence": 0.93,
                "needs_review": False,
            }),
            {},
        ),
    )
    @patch("tickets.services.whatsapp_service.send_whatsapp_notification")
    def test_whatsapp_generated_text_is_template_restricted_and_reviewed(
        self, send_whatsapp, generate, matches
    ):
        self.auto_settings.whatsapp_auto_reply = True
        self.auto_settings.simulation_mode = False
        self.auto_settings.save()
        ticket = self.make_ticket(source="whatsapp")

        audit_id = process_auto_resolution.run(ticket.pk)

        audit = AutoResolutionAudit.objects.get(pk=audit_id)
        self.assertEqual(audit.decision, "agent_review")
        self.assertEqual(audit.decision_reason, "whatsapp_template_restricted")
        self.assertEqual(audit.send_status, "unavailable")
        self.assertEqual(audit.provider_result, "template_restricted")
        send_whatsapp.assert_not_called()

    @override_settings(
        CELERY_TASK_ALWAYS_EAGER=True,
        WHATSAPP_ENABLED=True,
        WHATSAPP_PROVIDER="green_api",
        GREEN_API_URL="https://api.green-api.example",
        GREEN_API_MEDIA_URL="https://media.green-api.example",
        GREEN_API_INSTANCE_ID="test-instance",
        GREEN_API_TOKEN="test-token",
        GREEN_API_TIMEOUT_SECONDS=10,
    )
    @patch(
        "tickets.auto_resolution.find_similar_resolutions",
        return_value=[
            type("Match", (), {
                "ticket_id": 99,
                "problem": "Printer offline",
                "resolution": "Restart the printer.",
                "score": 0.94,
            })()
        ],
    )
    @patch(
        "tickets.auto_resolution.generate_with_openai",
        return_value=(
            json.dumps({
                "response": "Please restart the printer and let us know if it reconnects.",
                "confidence": 0.93,
                "needs_review": False,
            }),
            {},
        ),
    )
    @patch("whatsapp.services.send_whatsapp_message")
    @patch("whatsapp.services.get_state_instance")
    def test_eligible_whatsapp_auto_resolution_uses_green_api(
        self, get_state, send_message, generate, matches
    ):
        from whatsapp.services import GreenApiResult

        self.auto_settings.whatsapp_auto_reply = True
        self.auto_settings.simulation_mode = False
        self.auto_settings.save()
        ticket = self.make_ticket(source="whatsapp")
        self.add_whatsapp_contact(ticket)
        get_state.return_value = GreenApiResult("authorized")
        send_message.return_value = GreenApiResult(
            "sent", message_id="green-auto-response-id"
        )

        audit_id = process_auto_resolution.run(ticket.pk)

        audit = AutoResolutionAudit.objects.get(pk=audit_id)
        self.assertEqual(audit.decision, "auto_sent")
        self.assertEqual(audit.send_status, "sent")
        self.assertEqual(audit.provider_result, "green_api_accepted")
        self.assertEqual(audit.provider_message_id, "green-auto-response-id")
        self.assertEqual(audit.send_attempts, 1)
        self.assertEqual(
            send_message.call_args.args,
            ("+919876543210", audit.generated_response),
        )
        self.assertTrue(
            TicketMessage.objects.filter(
                ticket=ticket,
                ai_log=audit.ai_log,
                is_draft=False,
                body=audit.generated_response,
            ).exists()
        )

    @override_settings(
        CELERY_TASK_ALWAYS_EAGER=True,
        WHATSAPP_ENABLED=True,
        WHATSAPP_PROVIDER="green_api",
        GREEN_API_URL="https://api.green-api.example",
        GREEN_API_MEDIA_URL="https://media.green-api.example",
        GREEN_API_INSTANCE_ID="test-instance",
        GREEN_API_TOKEN="test-token",
        GREEN_API_TIMEOUT_SECONDS=10,
    )
    @patch(
        "tickets.auto_resolution.find_similar_resolutions",
        return_value=[
            type("Match", (), {
                "ticket_id": 99,
                "problem": "Printer offline",
                "resolution": "Restart the printer.",
                "score": 0.94,
            })()
        ],
    )
    @patch(
        "tickets.auto_resolution.generate_with_openai",
        return_value=(
            json.dumps({
                "response": "Please restart the printer and let us know if it reconnects.",
                "confidence": 0.93,
                "needs_review": True,
            }),
            {},
        ),
    )
    @patch("whatsapp.services.send_whatsapp_message")
    @patch("whatsapp.services.get_state_instance")
    def test_high_confidence_whatsapp_send_ignores_model_review_flag(
        self, get_state, send_message, generate, matches
    ):
        from whatsapp.services import GreenApiResult

        self.auto_settings.whatsapp_auto_reply = True
        self.auto_settings.simulation_mode = False
        self.auto_settings.save()
        ticket = self.make_ticket(source="whatsapp")
        self.add_whatsapp_contact(ticket)
        get_state.return_value = GreenApiResult("authorized")
        send_message.return_value = GreenApiResult(
            "sent", message_id="green-auto-response-id"
        )

        audit_id = process_auto_resolution.run(ticket.pk)

        audit = AutoResolutionAudit.objects.get(pk=audit_id)
        self.assertEqual(audit.decision, "auto_sent")
        self.assertEqual(audit.decision_reason, "confidence_and_safety_checks_passed")
        self.assertEqual(audit.send_status, "sent")
        get_state.assert_called_once()
        send_message.assert_called_once()

    @override_settings(
        CELERY_TASK_ALWAYS_EAGER=True,
        WHATSAPP_ENABLED=True,
        WHATSAPP_PROVIDER="green_api",
        GREEN_API_URL="https://api.green-api.example",
        GREEN_API_MEDIA_URL="https://media.green-api.example",
        GREEN_API_INSTANCE_ID="test-instance",
        GREEN_API_TOKEN="test-token",
        GREEN_API_TIMEOUT_SECONDS=10,
    )
    @patch(
        "tickets.auto_resolution.find_similar_resolutions",
        return_value=[
            type("Match", (), {
                "ticket_id": 99,
                "problem": "Printer offline",
                "resolution": "Restart the printer.",
                "score": 0.94,
            })()
        ],
    )
    @patch(
        "tickets.auto_resolution.generate_with_openai",
        return_value=(
            json.dumps({
                "response": "Please restart the printer and let us know if it reconnects.",
                "confidence": 0.93,
                "needs_review": False,
            }),
            {},
        ),
    )
    @patch("whatsapp.services.send_whatsapp_message")
    @patch("whatsapp.services.get_state_instance")
    def test_simulation_mode_never_sends_whatsapp(
        self, get_state, send_message, generate, matches
    ):
        self.auto_settings.whatsapp_auto_reply = True
        self.auto_settings.simulation_mode = True
        self.auto_settings.save()
        ticket = self.make_ticket(source="whatsapp")
        self.add_whatsapp_contact(ticket)

        audit_id = process_auto_resolution.run(ticket.pk)

        audit = AutoResolutionAudit.objects.get(pk=audit_id)
        self.assertEqual(audit.decision, "simulation")
        self.assertEqual(audit.send_status, "not_sent")
        get_state.assert_not_called()
        send_message.assert_not_called()

    @override_settings(
        CELERY_TASK_ALWAYS_EAGER=True,
        WHATSAPP_ENABLED=True,
        WHATSAPP_PROVIDER="green_api",
        GREEN_API_URL="https://api.green-api.example",
        GREEN_API_MEDIA_URL="https://media.green-api.example",
        GREEN_API_INSTANCE_ID="test-instance",
        GREEN_API_TOKEN="test-token",
        GREEN_API_TIMEOUT_SECONDS=10,
    )
    @patch(
        "tickets.auto_resolution.find_similar_resolutions",
        return_value=[
            type("Match", (), {
                "ticket_id": 99,
                "problem": "Printer offline",
                "resolution": "Restart the printer.",
                "score": 0.94,
            })()
        ],
    )
    @patch(
        "tickets.auto_resolution.generate_with_openai",
        return_value=(
            json.dumps({
                "response": "Please restart the printer and let us know if it reconnects.",
                "confidence": 0.93,
                "needs_review": False,
            }),
            {},
        ),
    )
    @patch("whatsapp.services.send_whatsapp_message")
    @patch("whatsapp.services.get_state_instance")
    def test_disabled_whatsapp_auto_reply_prevents_sending(
        self, get_state, send_message, generate, matches
    ):
        self.auto_settings.whatsapp_auto_reply = False
        self.auto_settings.simulation_mode = False
        self.auto_settings.save()
        ticket = self.make_ticket(source="whatsapp")
        self.add_whatsapp_contact(ticket)

        audit_id = process_auto_resolution.run(ticket.pk)

        audit = AutoResolutionAudit.objects.get(pk=audit_id)
        self.assertEqual(audit.decision_reason, "whatsapp_auto_reply_disabled")
        get_state.assert_not_called()
        send_message.assert_not_called()

    @override_settings(
        CELERY_TASK_ALWAYS_EAGER=True,
        WHATSAPP_ENABLED=True,
        WHATSAPP_PROVIDER="green_api",
        GREEN_API_URL="https://api.green-api.example",
        GREEN_API_MEDIA_URL="https://media.green-api.example",
        GREEN_API_INSTANCE_ID="test-instance",
        GREEN_API_TOKEN="test-token",
        GREEN_API_TIMEOUT_SECONDS=10,
    )
    @patch(
        "tickets.auto_resolution.find_similar_resolutions",
        return_value=[
            type("Match", (), {
                "ticket_id": 99,
                "problem": "Printer offline",
                "resolution": "Restart the printer.",
                "score": 0.94,
            })()
        ],
    )
    @patch(
        "tickets.auto_resolution.generate_with_openai",
        return_value=(
            json.dumps({
                "response": "Please restart the printer and let us know if it reconnects.",
                "confidence": 0.93,
                "needs_review": False,
            }),
            {},
        ),
    )
    @patch("whatsapp.services.send_whatsapp_message")
    @patch("whatsapp.services.get_state_instance")
    def test_green_api_failure_is_recorded_and_not_retried(
        self, get_state, send_message, generate, matches
    ):
        from whatsapp.services import GreenApiResult

        self.auto_settings.whatsapp_auto_reply = True
        self.auto_settings.simulation_mode = False
        self.auto_settings.save()
        ticket = self.make_ticket(source="whatsapp")
        self.add_whatsapp_contact(ticket)
        get_state.return_value = GreenApiResult("authorized")
        send_message.return_value = GreenApiResult(
            "error", error_code="http_503"
        )

        audit_id = process_auto_resolution.run(ticket.pk)
        audit = AutoResolutionAudit.objects.get(pk=audit_id)

        self.assertEqual(audit.decision, "agent_review")
        self.assertEqual(audit.decision_reason, "whatsapp_delivery_failed")
        self.assertEqual(audit.send_status, "failed")
        self.assertEqual(audit.send_error, "http_503")
        self.assertEqual(audit.provider_result, "green_api_delivery_failed")
        self.assertEqual(audit.send_attempts, 1)
        self.assertEqual(send_auto_resolution_whatsapp_task.run(audit.pk), "failed")
        send_message.assert_called_once()

    @override_settings(
        WHATSAPP_ENABLED=True,
        WHATSAPP_PROVIDER="green_api",
        GREEN_API_URL="https://api.green-api.example",
        GREEN_API_MEDIA_URL="https://media.green-api.example",
        GREEN_API_INSTANCE_ID="test-instance",
        GREEN_API_TOKEN="test-token",
        GREEN_API_TIMEOUT_SECONDS=10,
    )
    def test_whatsapp_delivery_retry_does_not_resend_sending_audit(self):
        from whatsapp.services import GreenApiResult

        self.auto_settings.whatsapp_auto_reply = True
        self.auto_settings.simulation_mode = False
        self.auto_settings.save()
        ticket = self.make_ticket(source="whatsapp")
        self.add_whatsapp_contact(ticket)
        audit = AutoResolutionAudit.objects.create(
            ticket=ticket,
            channel="whatsapp",
            decision="auto_send",
            send_status="sending",
            generated_response="Please restart the printer.",
        )

        with (
            patch(
                "whatsapp.services.get_state_instance",
                return_value=GreenApiResult("authorized"),
            ) as state_mock,
            patch("whatsapp.services.send_whatsapp_message") as send_mock,
        ):
            result = send_auto_resolution_whatsapp_task.run(audit.pk)

        audit.refresh_from_db()
        self.assertEqual(result, "failed")
        self.assertEqual(audit.decision_reason, "delivery_outcome_unknown")
        self.assertEqual(audit.send_status, "failed")
        state_mock.assert_not_called()
        send_mock.assert_not_called()

    @override_settings(
        WHATSAPP_ENABLED=True,
        WHATSAPP_PROVIDER="green_api",
        GREEN_API_URL="https://api.green-api.example",
        GREEN_API_MEDIA_URL="https://media.green-api.example",
        GREEN_API_INSTANCE_ID="test-instance",
        GREEN_API_TOKEN="test-token",
        GREEN_API_TIMEOUT_SECONDS=10,
    )
    def test_sent_whatsapp_delivery_is_idempotent(self):
        from whatsapp.services import GreenApiResult

        self.auto_settings.whatsapp_auto_reply = True
        self.auto_settings.simulation_mode = False
        self.auto_settings.save()
        ticket = self.make_ticket(source="whatsapp")
        self.add_whatsapp_contact(ticket)
        audit = AutoResolutionAudit.objects.create(
            ticket=ticket,
            channel="whatsapp",
            decision="auto_sent",
            send_status="sent",
            generated_response="Please restart the printer.",
            provider_message_id="previously-sent-id",
        )

        with (
            patch(
                "whatsapp.services.get_state_instance",
                return_value=GreenApiResult("authorized"),
            ) as state_mock,
            patch("whatsapp.services.send_whatsapp_message") as send_mock,
        ):
            result = send_auto_resolution_whatsapp_task.run(audit.pk)

        self.assertEqual(result, "sent")
        state_mock.assert_not_called()
        send_mock.assert_not_called()

    def test_off_switch_is_read_from_database_and_prevents_processing(self):
        self.auto_settings.enabled = False
        self.auto_settings.save()
        ticket = self.make_ticket()

        result = process_auto_resolution.run(ticket.pk)

        self.assertEqual(result, ticket.pk)
        self.assertFalse(AutoResolutionAudit.objects.filter(ticket=ticket).exists())

    def test_replayed_pending_delivery_does_not_send_twice(self):
        self.auto_settings.simulation_mode = False
        self.auto_settings.save()
        ticket = self.make_ticket()
        audit = AutoResolutionAudit.objects.create(
            ticket=ticket,
            channel="email",
            decision="auto_send",
            send_status="sending",
            generated_response="Please restart the printer and reconnect it to the network.",
        )

        result = send_auto_resolution_email_task.run(audit.pk)

        audit.refresh_from_db()
        self.assertEqual(result, "failed")
        self.assertEqual(audit.send_status, "failed")
        self.assertEqual(audit.decision_reason, "delivery_outcome_unknown")
        self.assertEqual(len(mail.outbox), 0)

    def test_admin_can_update_runtime_controls_and_statistics(self):
        from accounts.models import User

        admin = User.objects.create_user(
            username="auto-resolution-admin",
            password="test-password",
            role="ADMIN",
            is_staff=True,
        )
        client = APIClient()
        client.force_authenticate(admin)

        response = client.patch(
            "/api/admin/auto-resolution/",
            {
                "enabled": True,
                "email_auto_reply": False,
                "whatsapp_auto_reply": True,
                "simulation_mode": True,
                "minimum_threshold": 0.9,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.auto_settings.refresh_from_db()
        self.assertTrue(self.auto_settings.enabled)
        self.assertFalse(self.auto_settings.email_auto_reply)
        self.assertTrue(self.auto_settings.whatsapp_auto_reply)
        self.assertEqual(self.auto_settings.minimum_threshold, 0.9)
        self.assertEqual(self.auto_settings.changed_by, admin)
        self.assertEqual(AutoResolutionSettings.objects.count(), 1)
        self.assertIn("changed_at", response.data)
        self.assertIn("stats", response.data)

        read_response = client.get("/api/admin/auto-resolution/")
        self.assertEqual(read_response.status_code, 200)
        self.assertIs(read_response.data["enabled"], True)
        self.assertEqual(read_response.data["minimum_threshold"], 0.9)

        off_response = client.patch(
            "/api/admin/auto-resolution/",
            {"enabled": False},
            format="json",
        )
        self.assertEqual(off_response.status_code, 200)
        self.auto_settings.refresh_from_db()
        self.assertFalse(self.auto_settings.enabled)
        refreshed_response = client.get("/api/admin/auto-resolution/")
        self.assertIs(refreshed_response.data["enabled"], False)
        self.assertEqual(AutoResolutionSettings.objects.count(), 1)

    def test_agent_cannot_change_runtime_controls(self):
        from accounts.models import User

        agent = User.objects.create_user(
            username="auto-resolution-agent",
            password="test-password",
            role=User.ROLE_AGENT,
        )
        client = APIClient()
        client.force_authenticate(agent)

        response = client.patch(
            "/api/admin/auto-resolution/",
            {"enabled": True},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_admin_setting_changes_are_visible_to_background_worker(self):
        from accounts.models import User

        admin = User.objects.create_user(
            username="worker-setting-admin",
            password="test-password",
            role="ADMIN",
            is_staff=True,
        )
        client = APIClient()
        client.force_authenticate(admin)
        client.patch("/api/admin/auto-resolution/", {"enabled": False}, format="json")
        ticket = self.make_ticket()

        result = process_auto_resolution.run(ticket.pk)

        self.assertEqual(result, ticket.pk)
        self.assertFalse(AutoResolutionAudit.objects.filter(ticket=ticket).exists())

    @patch("tickets.auto_resolution.find_similar_resolutions", return_value=[])
    def test_enabled_setting_written_by_admin_api_is_seen_by_worker(self, find_matches):
        from accounts.models import User

        admin = User.objects.create_user(
            username="worker-enabled-admin",
            password="test-password",
            role="ADMIN",
            is_staff=True,
        )
        client = APIClient()
        client.force_authenticate(admin)
        response = client.patch(
            "/api/admin/auto-resolution/",
            {"enabled": True},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        ticket = self.make_ticket()

        audit_id = process_auto_resolution.run(ticket.pk)

        audit = AutoResolutionAudit.objects.get(pk=audit_id)
        self.assertEqual(audit.decision_reason, "no_similar_resolved_case")
        find_matches.assert_called_once()

    def test_agent_can_read_auto_resolution_audit(self):
        ticket = self.make_ticket()
        audit = AutoResolutionAudit.objects.create(
            ticket=ticket,
            decision="agent_review",
            decision_reason="confidence_below_threshold",
        )
        response = APIClient()
        from accounts.models import User

        agent = User.objects.create_user(
            username="resolution-agent",
            password="agentpass",
            role=User.ROLE_AGENT,
        )
        response.force_login(agent)

        result = response.get(f"/api/tickets/{ticket.pk}/auto-resolution/")

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["decision"], audit.decision)
        self.assertEqual(result.data["decision_reason"], audit.decision_reason)
