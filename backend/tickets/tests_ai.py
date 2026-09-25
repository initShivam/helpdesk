from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User

from .ai import AIAnalysisError, analyze_ticket, enrich_ticket
from .models import Ticket


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
