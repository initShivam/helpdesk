from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User

from .ai import AIAnalysisError, analyze_ticket, enrich_ticket
from .ai_service import build_prompt, sanitize_prompt
from .models import AILog, Ticket, TicketMessage
from .tasks import generate_ai_suggestion
from knowledge_base.services import index_document


class TicketAIAnalysisTests(TestCase):
    def test_classifies_technical_ticket(self):
        analysis = analyze_ticket(
            "Printer error",
            "The office printer is not working and shows an error.",
        )

        self.assertEqual(analysis.category, "technical")
        self.assertGreaterEqual(analysis.confidence, 0)
        self.assertLessEqual(analysis.confidence, 1)
        self.assertEqual(
            analysis.summary,
            "The office printer is not working and shows an error.",
        )

    def test_classifies_refund_ticket(self):
        analysis = analyze_ticket("Refund request", "Please refund this payment.")

        self.assertEqual(analysis.category, "refund")
        self.assertGreaterEqual(analysis.confidence, 0)
        self.assertLessEqual(analysis.confidence, 1)

    def test_assigns_high_priority_to_urgent_ticket(self):
        analysis = analyze_ticket(
            "Cannot access exam portal",
            "The system is down and my exam is today. Please help ASAP.",
        )

        self.assertEqual(analysis.priority, "high")

    def test_assigns_low_priority_to_non_urgent_request(self):
        analysis = analyze_ticket(
            "Product suggestion",
            "When possible, please consider this feedback.",
        )

        self.assertEqual(analysis.priority, "low")

    def test_assigns_medium_priority_by_default(self):
        analysis = analyze_ticket("Printer issue", "The printer is not working.")

        self.assertEqual(analysis.priority, "medium")

    def test_unmatched_ticket_defaults_to_general(self):
        analysis = analyze_ticket("Welcome", "I would like to contact support.")

        self.assertEqual(analysis.category, "general")
        self.assertEqual(analysis.confidence, 0.5)

    def test_summary_uses_body_and_is_bounded(self):
        body = " ".join(["A very long student report"] * 100)
        analysis = analyze_ticket("Issue", body)

        self.assertTrue(analysis.summary.startswith("A very long student report"))
        self.assertLessEqual(len(analysis.summary), 240)

    def test_manual_ticket_creation_runs_analysis(self):
        user = User.objects.create_user(
            username="agent",
            password="password",
            role="AGENT",
        )
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.post(
            "/api/tickets/",
            {
                "ticket_number": "AI-001",
                "subject": "Payment refund",
                "requester_email": "customer@example.com",
                "priority": "medium",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        ticket = Ticket.objects.get(ticket_number="AI-001")
        self.assertEqual(ticket.category, "refund")
        self.assertEqual(ticket.priority, "medium")
        self.assertTrue(ticket.ai_summary)
        self.assertIsNotNone(ticket.ai_category_confidence)

    def test_analysis_failure_does_not_block_ticket_creation(self):
        ticket = Ticket.objects.create(
            ticket_number="AI-002",
            subject="Needs review",
            requester_email="customer@example.com",
        )
        with patch(
            "tickets.ai.analyze_ticket",
            side_effect=AIAnalysisError("analyzer unavailable"),
        ):
            succeeded = enrich_ticket(ticket)

        self.assertFalse(succeeded)
        ticket.refresh_from_db()
        self.assertIsNone(ticket.ai_summary)
        self.assertIsNone(ticket.ai_category_confidence)

    def test_unexpected_analysis_failure_does_not_block_ticket_creation(self):
        ticket = Ticket.objects.create(
            ticket_number="AI-003",
            subject="Needs review",
            requester_email="customer@example.com",
        )
        with patch(
            "tickets.ai.analyze_ticket",
            side_effect=RuntimeError("unexpected analyzer failure"),
        ):
            succeeded = enrich_ticket(ticket)

        self.assertFalse(succeeded)
        ticket.refresh_from_db()
        self.assertEqual(ticket.category, "general")
        self.assertEqual(ticket.priority, "medium")
        self.assertIsNone(ticket.ai_summary)
        self.assertIsNone(ticket.ai_category_confidence)

    def test_safety_filter_redacts_pii_and_profanity(self):
        sanitized = sanitize_prompt("Email me at user@example.com or call +1 555-123-4567, shit.")

        self.assertNotIn("user@example.com", sanitized)
        self.assertNotIn("555-123-4567", sanitized)
        self.assertNotIn("shit", sanitized.lower())

    @patch("tickets.tasks.generate_with_gemini")
    def test_generate_suggestion_retrieves_context_and_creates_draft(self, generate):
        ticket = Ticket.objects.create(
            ticket_number="AI-SUGGEST-001",
            subject="How do I reset my password?",
            requester_email="customer@example.com",
        )
        TicketMessage.objects.create(
            ticket=ticket,
            body="I cannot sign in and need a password reset.",
            message_type="customer",
        )
        document = index_document(
            title="Password reset",
            content="Customers can reset a forgotten password from account security.",
        )
        generate.return_value = ("Use the account security page to reset your password.", {"totalTokenCount": 20})

        log_id = generate_ai_suggestion.run(ticket.pk)

        log = AILog.objects.get(pk=log_id)
        draft = TicketMessage.objects.get(ticket=ticket, is_ai_generated=True)
        self.assertEqual(log.status, "succeeded")
        self.assertEqual(log.retrieved_document_ids, [document.pk])
        self.assertTrue(draft.is_draft)
        self.assertEqual(draft.body, generate.return_value[0])
        generate.assert_called_once()

    @patch("tickets.tasks.generate_with_gemini", side_effect=RuntimeError("provider down"))
    def test_generate_suggestion_records_failure(self, generate):
        ticket = Ticket.objects.create(
            ticket_number="AI-SUGGEST-002",
            subject="Need help",
            requester_email="customer@example.com",
        )

        with self.assertRaises(RuntimeError):
            generate_ai_suggestion.run(ticket.pk)

        log = AILog.objects.get(ticket=ticket)
        self.assertEqual(log.status, "failed")

    def test_prompt_contains_ticket_and_retrieved_context(self):
        ticket = Ticket(
            subject="Refund status",
        )
        message = TicketMessage(body="Please check my refund.", message_type="customer")

        prompt = build_prompt(ticket, [message], [])

        self.assertIn("Refund status", prompt)
        self.assertIn("Please check my refund.", prompt)

    @patch("tickets.views.generate_ai_suggestion.delay", return_value=SimpleNamespace(id="task-1"))
    def test_suggestion_endpoint_queues_task_and_accepts_draft(self, delay):
        user = User.objects.create_user(username="reviewer", password="ReviewerPass123!", role="AGENT")
        ticket = Ticket.objects.create(
            ticket_number="AI-SUGGEST-003",
            subject="Need a reply",
            requester_email="customer@example.com",
        )
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.post(f"/api/tickets/{ticket.pk}/suggest-reply/")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["task_id"], "task-1")
        delay.assert_called_once_with(ticket.pk)

        draft = TicketMessage.objects.create(
            ticket=ticket,
            body="Draft response",
            message_type="agent",
            is_ai_generated=True,
            is_draft=True,
        )
        response = client.post(
            f"/api/tickets/{ticket.pk}/accept-suggestion/",
            {"message_id": draft.pk, "body": "Edited response"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        draft.refresh_from_db()
        self.assertEqual(draft.body, "Edited response")
        self.assertFalse(draft.is_ai_generated)
        self.assertFalse(draft.is_draft)
