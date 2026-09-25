from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from accounts.models import User
from tickets.models import Ticket, TicketMessage

class TicketMessageAPITest(TestCase):
    def setUp(self):
        # users
        self.admin = User.objects.create_user(username='admin', password='adminpass', role='ADMIN', is_staff=True)
        self.agent = User.objects.create_user(username='agent', password='agentpass', role='AGENT')
        # ticket
        self.ticket = Ticket.objects.create(
            ticket_number='TCKT-001',
            subject='Test Ticket',
            requester_email='test@example.com',
            status='open',
            category='general',
            priority='medium',
            created_by=self.admin,
        )
        # another ticket for cross‑ticket tests
        self.other_ticket = Ticket.objects.create(
            ticket_number='TCKT-002',
            subject='Other Ticket',
            requester_email='other@example.com',
            status='open',
            category='general',
            priority='medium',
            created_by=self.admin,
        )
        # a message belonging to self.ticket, created by admin
        self.message = TicketMessage.objects.create(
            ticket=self.ticket,
            sender=self.admin,
            body='Initial message',
            message_type='agent',
        )
        self.client = APIClient()

    def _list_url(self, ticket_id):
        return f'/api/tickets/{ticket_id}/messages/'

    def _detail_url(self, ticket_id, msg_id):
        return f'/api/tickets/{ticket_id}/messages/{msg_id}/'

    def test_unauthenticated_access(self):
        resp = self.client.get(self._list_url(self.ticket.id))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_agent_list_messages(self):
        self.client.login(username='agent', password='agentpass')
        resp = self.client.get(self._list_url(self.ticket.id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(resp.data), 1)
        self.client.logout()

    def test_admin_list_messages(self):
        self.client.login(username='admin', password='adminpass')
        resp = self.client.get(self._list_url(self.ticket.id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.client.logout()

    def test_agent_create_message_sender_auto(self):
        self.client.login(username='agent', password='agentpass')
        data = {'body': 'Agent reply', 'message_type': 'agent'}
        resp = self.client.post(self._list_url(self.ticket.id), data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # sender should be the logged‑in user
        self.assertEqual(resp.data['sender'], self.agent.id)
        self.client.logout()

    def test_admin_create_message(self):
        self.client.login(username='admin', password='adminpass')
        data = {'body': 'Admin note', 'message_type': 'agent'}
        resp = self.client.post(self._list_url(self.ticket.id), data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['sender'], self.admin.id)
        self.client.logout()

    def test_retrieve_message(self):
        self.client.login(username='agent', password='agentpass')
        resp = self.client.get(self._detail_url(self.ticket.id, self.message.id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['id'], self.message.id)
        self.client.logout()

    def test_agent_update_message(self):
        self.client.login(username='agent', password='agentpass')
        # agent is allowed to update any message they own? For simplicity we allow update if role is AGENT
        data = {'body': 'Updated by agent'}
        resp = self.client.patch(self._detail_url(self.ticket.id, self.message.id), data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['body'], 'Updated by agent')
        self.client.logout()

    def test_agent_cannot_delete_message(self):
        self.client.login(username='agent', password='agentpass')
        resp = self.client.delete(self._detail_url(self.ticket.id, self.message.id))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.client.logout()

    def test_admin_delete_message(self):
        self.client.login(username='admin', password='adminpass')
        resp = self.client.delete(self._detail_url(self.ticket.id, self.message.id))
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.client.logout()

    def test_invalid_ticket_returns_404(self):
        self.client.login(username='agent', password='agentpass')
        resp = self.client.get(self._list_url(9999))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.client.logout()

    def test_cross_ticket_access_rejected(self):
        self.client.login(username='agent', password='agentpass')
        # try to access the message via a different ticket id
        resp = self.client.get(self._detail_url(self.other_ticket.id, self.message.id))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.client.logout()

    def test_invalid_message_body_returns_400(self):
        self.client.login(username='agent', password='agentpass')
        data = {'body': '', 'message_type': 'agent'}  # empty body should be invalid (serializer requires non‑blank)
        resp = self.client.post(self._list_url(self.ticket.id), data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.client.logout()
