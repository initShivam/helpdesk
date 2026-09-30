from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User

from datetime import timedelta
from django.utils import timezone
from .ai import AIAnalysisError, analyze_ticket, enrich_ticket
from .ai_service import (
    build_classification_prompt,
    build_prompt,
    build_summary_prompt,
    parse_classification_response,
    sanitize_prompt,
)
from .models import AILog, Ticket, TicketMessage
from .tasks import classify_ticket, generate_ai_suggestion, summarize_ticket
from knowledge_base.services import index_document


@override_settings(GEMINI_API_KEY='')
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


class Phase4ClassificationSummariesDashboardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testagent",
            password="AgentPassword123!",
            role="AGENT",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch("tickets.tasks.generate_with_gemini")
    def test_classify_ticket_task_success(self, mock_gemini):
        mock_gemini.return_value = ("technical", {"totalTokenCount": 35})
        ticket = Ticket.objects.create(
            ticket_number="PHASE4-001",
            subject="VPN connection repeatedly drops with TLS handshake failure",
            description="The desktop VPN client disconnects every 5 minutes.",
            requester_email="tech@example.com",
            category="general",
        )

        predicted = classify_ticket.run(ticket.pk)

        self.assertEqual(predicted, "technical")
        ticket.refresh_from_db()
        self.assertEqual(ticket.category, "technical")
        self.assertEqual(ticket.classification, "technical")
        self.assertEqual(ticket.ai_category_confidence, 0.95)

        log = AILog.objects.get(ticket=ticket, operation="classify")
        self.assertEqual(log.status, "succeeded")
        self.assertEqual(log.response_text, "technical")
        self.assertIn("Few-shot examples", log.sanitized_prompt)
        self.assertIn("VPN connection repeatedly drops", log.sanitized_prompt)
        mock_gemini.assert_called_once()

    @patch("tickets.tasks.generate_with_gemini")
    def test_classify_ticket_task_refund_category(self, mock_gemini):
        mock_gemini.return_value = ("Category: refund", {})
        ticket = Ticket.objects.create(
            ticket_number="PHASE4-002",
            subject="Request a refund for erroneous billing",
            description="Please refund the extra $49 charged to my account.",
            requester_email="billing@example.com",
            category="general",
        )

        predicted = classify_ticket.run(ticket.pk)

        self.assertEqual(predicted, "refund")
        ticket.refresh_from_db()
        self.assertEqual(ticket.category, "refund")
        self.assertEqual(ticket.classification, "refund")

    @patch("tickets.tasks.generate_with_gemini", side_effect=RuntimeError("Gemini unavailable"))
    def test_classify_ticket_task_failure_records_log(self, mock_gemini):
        ticket = Ticket.objects.create(
            ticket_number="PHASE4-003",
            subject="System down",
            requester_email="user@example.com",
        )

        with self.assertRaises(RuntimeError):
            classify_ticket.run(ticket.pk)

        log = AILog.objects.get(ticket=ticket, operation="classify")
        self.assertEqual(log.status, "failed")
        self.assertIn("Gemini unavailable", log.error_message)

    @patch("tickets.tasks.generate_with_gemini")
    def test_summarize_ticket_task_success(self, mock_gemini):
        summary_text = "Customer encountered 403 forbidden error during SSO login; advised admin credential reset."
        mock_gemini.return_value = (summary_text, {"totalTokenCount": 50})
        ticket = Ticket.objects.create(
            ticket_number="PHASE4-004",
            subject="Cannot log in with SSO",
            description="Getting a 403 Forbidden page when logging in via Okta.",
            requester_email="sso@example.com",
        )
        TicketMessage.objects.create(
            ticket=ticket,
            body="Getting a 403 Forbidden page when logging in via Okta.",
            message_type="customer",
        )

        result = summarize_ticket.run(ticket.pk)

        self.assertEqual(result, summary_text)
        ticket.refresh_from_db()
        self.assertEqual(ticket.ai_summary, summary_text)

        msg = TicketMessage.objects.get(ticket=ticket, message_type="system", is_ai_generated=True)
        self.assertEqual(msg.body, summary_text)
        self.assertFalse(msg.is_draft)

        log = AILog.objects.get(ticket=ticket, operation="summarize")
        self.assertEqual(log.status, "succeeded")
        self.assertEqual(log.response_text, summary_text)
        self.assertIn("403 Forbidden", log.sanitized_prompt)

    @patch("tickets.tasks.generate_with_gemini", side_effect=RuntimeError("AI summary timeout"))
    def test_summarize_ticket_task_failure_records_log(self, mock_gemini):
        ticket = Ticket.objects.create(
            ticket_number="PHASE4-005",
            subject="Timeout issue",
            requester_email="user@example.com",
        )

        with self.assertRaises(RuntimeError):
            summarize_ticket.run(ticket.pk)

        log = AILog.objects.get(ticket=ticket, operation="summarize")
        self.assertEqual(log.status, "failed")
        self.assertIn("AI summary timeout", log.error_message)

    @patch("tickets.views.classify_ticket.delay", return_value=SimpleNamespace(id="task-classify-1"))
    def test_classify_endpoint_queues_task(self, mock_delay):
        ticket = Ticket.objects.create(
            ticket_number="PHASE4-006",
            subject="Need classification",
            requester_email="test@example.com",
        )
        response = self.client.post(f"/api/tickets/{ticket.pk}/classify/")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["task_id"], "task-classify-1")
        mock_delay.assert_called_once_with(ticket.pk)

    @patch("tickets.views.summarize_ticket.delay", return_value=SimpleNamespace(id="task-summary-1"))
    def test_summarize_endpoint_queues_task(self, mock_delay):
        ticket = Ticket.objects.create(
            ticket_number="PHASE4-007",
            subject="Need summary",
            requester_email="test@example.com",
        )
        response = self.client.post(f"/api/tickets/{ticket.pk}/summarize/")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["task_id"], "task-summary-1")
        mock_delay.assert_called_once_with(ticket.pk)

    def test_analytics_overview_unauthenticated_returns_401(self):
        anon_client = APIClient()
        response = anon_client.get("/api/analytics/overview")
        self.assertEqual(response.status_code, 401)
        response_slash = anon_client.get("/api/analytics/overview/")
        self.assertEqual(response_slash.status_code, 401)

    def test_analytics_overview_metrics_accuracy(self):
        now = timezone.now()

        # Ticket 1 created 1 hour ago, first reply 40 minutes ago (reply time = 20 min = 1200 sec)
        t1 = Ticket.objects.create(
            ticket_number="METRIC-001",
            subject="Issue 1",
            requester_email="user1@example.com",
            category="technical",
            priority="high",
            status="resolved",
        )
        Ticket.objects.filter(pk=t1.pk).update(created_at=now - timedelta(minutes=60))
        t1.refresh_from_db()
        m1 = TicketMessage.objects.create(
            ticket=t1,
            body="First agent response to issue 1",
            message_type="agent",
            is_draft=False,
            is_ai_generated=False,
        )
        TicketMessage.objects.filter(pk=m1.pk).update(created_at=now - timedelta(minutes=40))

        # Ticket 2 created 2 hours ago, first reply 80 minutes ago (reply time = 40 min = 2400 sec)
        t2 = Ticket.objects.create(
            ticket_number="METRIC-002",
            subject="Issue 2",
            requester_email="user2@example.com",
            category="refund",
            priority="medium",
            status="open",
        )
        Ticket.objects.filter(pk=t2.pk).update(created_at=now - timedelta(minutes=120))
        t2.refresh_from_db()
        m2 = TicketMessage.objects.create(
            ticket=t2,
            body="First agent response to issue 2",
            message_type="agent",
            is_draft=False,
            is_ai_generated=False,
        )
        TicketMessage.objects.filter(pk=m2.pk).update(created_at=now - timedelta(minutes=80))

        # Average reply time should be (1200 + 2400) / 2 = 1800 sec = 30 minutes
        # Setup AI logs: 2 suggestions generated, 1 accepted
        ai_log1 = AILog.objects.create(
            ticket=t1,
            model="gemini-2.0-flash",
            operation="suggest_reply",
            status="succeeded",
        )
        # Message accepted
        TicketMessage.objects.create(
            ticket=t1,
            body="Accepted suggestion",
            message_type="agent",
            is_ai_generated=False,
            is_draft=False,
            ai_log=ai_log1,
        )

        ai_log2 = AILog.objects.create(
            ticket=t2,
            model="gemini-2.0-flash",
            operation="suggest_reply",
            status="succeeded",
        )
        # Message still in draft
        TicketMessage.objects.create(
            ticket=t2,
            body="Draft pending suggestion",
            message_type="agent",
            is_ai_generated=True,
            is_draft=True,
            ai_log=ai_log2,
        )

        response = self.client.get("/api/analytics/overview")
        self.assertEqual(response.status_code, 200)
        data = response.data

        self.assertGreaterEqual(data["total_tickets"], 2)
        self.assertGreaterEqual(data["open_tickets"], 1)
        self.assertGreaterEqual(data["resolved_tickets"], 1)
        # Verify first reply time
        self.assertEqual(data["average_first_reply_time_seconds"], 1800.0)
        self.assertEqual(data["average_first_reply_time_minutes"], 30.0)
        self.assertEqual(data["average_first_reply_time_formatted"], "30m")

        # Verify AI acceptance
        ai_stats = data["ai_suggestions"]
        self.assertEqual(ai_stats["total"], 2)
        self.assertEqual(ai_stats["accepted"], 1)
        self.assertEqual(ai_stats["acceptance_rate"], 50.0)

        # Verify tickets per day
        self.assertIsInstance(data["tickets_per_day"], list)
        self.assertTrue(len(data["tickets_per_day"]) >= 14)
        total_in_trend = sum(item["count"] for item in data["tickets_per_day"])
        self.assertGreaterEqual(total_in_trend, 2)

        # Verify categories & priorities
        cats = {item["category"]: item["count"] for item in data["categories"]}
        self.assertGreaterEqual(cats["technical"], 1)
        self.assertGreaterEqual(cats["refund"], 1)

    def test_ticket_list_category_filter_and_ordering(self):
        Ticket.objects.create(
            ticket_number="FILTER-TECH-01",
            subject="Tech issue",
            requester_email="tech@example.com",
            category="technical",
        )
        Ticket.objects.create(
            ticket_number="FILTER-REF-01",
            subject="Refund issue",
            requester_email="ref@example.com",
            category="refund",
        )

        # Filter by category
        res = self.client.get("/api/tickets/?category=technical")
        self.assertEqual(res.status_code, 200)
        tickets = res.data if isinstance(res.data, list) else res.data["results"]
        ticket_numbers = [t["ticket_number"] for t in tickets]
        self.assertIn("FILTER-TECH-01", ticket_numbers)
        self.assertNotIn("FILTER-REF-01", ticket_numbers)

        # Verify classification field in response matches category
        tech_ticket = next(t for t in tickets if t["ticket_number"] == "FILTER-TECH-01")
        self.assertEqual(tech_ticket["classification"], "technical")
        self.assertEqual(tech_ticket["category"], "technical")

        # Ordering by created_at ascending
        res_asc = self.client.get("/api/tickets/?ordering=created_at")
        self.assertEqual(res_asc.status_code, 200)

        # Ordering by created_at descending
        res_desc = self.client.get("/api/tickets/?ordering=-created_at")
        self.assertEqual(res_desc.status_code, 200)

