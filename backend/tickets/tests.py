from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from accounts.models import User

class TicketAPIPermissionsTest(TestCase):
    def setUp(self):
        # Create admin user
        self.admin_user = User.objects.create_user(
            username='admin', password='adminpass', role='ADMIN', is_staff=True
        )
        # Create agent user
        self.agent_user = User.objects.create_user(
            username='agent', password='agentpass', role='AGENT'
        )
        # Create a ticket for later retrieval
        from tickets.models import Ticket
        self.ticket = Ticket.objects.create(
            ticket_number='TCKT-001',
            subject='Test Ticket',
            requester_email='test@example.com',
            status='open',
            category='general',
            priority='medium',
            created_by=self.admin_user,
        )
        self.client = APIClient()

    def test_unauthenticated_access(self):
        response = self.client.get('/api/tickets/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_agent_full_access_without_delete(self):
        self.client.login(username='agent', password='agentpass')
        # List
        resp = self.client.get('/api/tickets/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Retrieve
        resp = self.client.get(f'/api/tickets/{self.ticket.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Create
        data = {
            "ticket_number": "TCKT-002",
            "subject": "New ticket",
            "description": "A detailed ticket description.",
            "requester_email": "new@example.com",
            "status": "open",
            "category": "general",
            "priority": "low",
        }
        resp = self.client.post('/api/tickets/', data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["description"], "A detailed ticket description.")
        new_id = resp.data['id']
        # Update
        update_data = {"status": "resolved"}
        resp = self.client.patch(f'/api/tickets/{new_id}/', update_data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Delete should be forbidden
        resp = self.client.delete(f'/api/tickets/{new_id}/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.client.logout()

    def test_ticket_list_supports_filters_search_and_ordering(self):
        from tickets.models import Ticket

        Ticket.objects.create(
            ticket_number="TCKT-LOW",
            subject="Printer issue",
            description="Printer is offline.",
            requester_email="printer@example.com",
            status="resolved",
            category="technical",
            priority="low",
        )
        self.client.login(username="agent", password="agentpass")

        filtered = self.client.get("/api/tickets/?status=resolved&category=technical")
        self.assertEqual(filtered.status_code, status.HTTP_200_OK)
        self.assertEqual(len(filtered.data["results"]), 1)
        self.assertEqual(filtered.data["results"][0]["ticket_number"], "TCKT-LOW")

        searched = self.client.get("/api/tickets/?search=Printer")
        self.assertEqual(searched.status_code, status.HTTP_200_OK)
        self.assertEqual(searched.data["results"][0]["ticket_number"], "TCKT-LOW")

        ordered = self.client.get("/api/tickets/?ordering=created_at")
        self.assertEqual(ordered.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {ticket["ticket_number"] for ticket in ordered.data["results"]},
            {"TCKT-001", "TCKT-LOW"},
        )

    def test_admin_can_delete(self):
        self.client.login(username='admin', password='adminpass')
        # Create a ticket to delete
        data = {
            "ticket_number": "TCKT-003",
            "subject": "Delete me",
            "requester_email": "del@example.com",
            "status": "open",
            "category": "general",
            "priority": "low",
        }
        resp = self.client.post('/api/tickets/', data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        ticket_id = resp.data['id']
        # Delete
        resp = self.client.delete(f'/api/tickets/{ticket_id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.client.logout()

    def test_agent_cannot_access_user_management(self):
        self.client.login(username='agent', password='agentpass')
        resp = self.client.get('/api/agents/')  # assuming agents endpoint
        # Expect 403 or 404 depending on routing; we assert not 200
        self.assertNotEqual(resp.status_code, status.HTTP_200_OK)
        self.client.logout()
