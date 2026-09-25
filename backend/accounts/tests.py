from django.test import TestCase
from rest_framework.test import APIClient

from .models import User


class AuthenticationAndUserManagementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="adminpass",
            role=User.ROLE_ADMIN,
        )
        self.client = APIClient(enforce_csrf_checks=True)

    def _csrf_headers(self):
        self.client.get("/api/auth/me/")
        return {"HTTP_X_CSRFTOKEN": self.client.cookies["csrftoken"].value}

    def test_login_requires_csrf_token(self):
        response = self.client.post(
            "/api/auth/login/",
            {"username": "admin", "password": "adminpass"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_csrf_endpoint_returns_token(self):
        response = self.client.get("/api/auth/csrf/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["csrfToken"])
        self.assertIn("csrftoken", self.client.cookies)

    def test_login_accepts_email_address(self):
        self.client.get("/api/auth/me/")
        csrf_token = self.client.cookies["csrftoken"].value
        response = self.client.post(
            "/api/auth/login/",
            {"email": "admin@example.com", "password": "adminpass"},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("password", response.data)
        self.assertIn("sessionid", self.client.cookies)
        self.assertNotIn("access", response.data)
        self.assertNotIn("refresh", response.data)

    def test_admin_can_create_user_with_login_ready_password(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            "/api/agents/",
            {
                "username": "new-agent",
                "email": "agent@example.com",
                "role": User.ROLE_AGENT,
                "password": "AgentPass123!",
            },
            format="json",
            **self._csrf_headers(),
        )
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(username="new-agent")
        self.assertTrue(user.check_password("AgentPass123!"))

    def test_confidence_must_be_between_zero_and_one(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            "/api/tickets/",
            {
                "ticket_number": "TCKT-CONF",
                "subject": "Confidence test",
                "requester_email": "requester@example.com",
                "ai_category_confidence": 1.1,
            },
            format="json",
            **self._csrf_headers(),
        )
        self.assertEqual(response.status_code, 400)
