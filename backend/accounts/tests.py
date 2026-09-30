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

        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["email"], "admin@example.com")
        self.assertEqual(response.data["role"], User.ROLE_ADMIN)

    def test_login_rotates_the_anonymous_session_key(self):
        csrf_token = self.client.get("/api/auth/csrf/").data["csrfToken"]
        session = self.client.session
        session["pre_login_value"] = "preserved"
        session.save()
        old_session_key = session.session_key
        self.client.cookies["sessionid"] = old_session_key

        response = self.client.post(
            "/api/auth/login/",
            {"username": "admin", "password": "adminpass"},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(
            old_session_key,
            self.client.cookies["sessionid"].value,
        )
        self.assertEqual(self.client.session.get("pre_login_value"), "preserved")

    def test_logout_revokes_the_session(self):
        csrf_token = self.client.get("/api/auth/csrf/").data["csrfToken"]
        response = self.client.post(
            "/api/auth/login/",
            {"username": "admin", "password": "adminpass"},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.client.cookies["sessionid"].value)

        csrf_token = self.client.get("/api/auth/csrf/").data["csrfToken"]
        response = self.client.post(
            "/api/auth/logout/",
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

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

    def test_agent_management_cannot_create_or_delete_admins(self):
        self.client.force_login(self.admin)
        agent = User.objects.create_user(
            username="existing-agent",
            email="existing-agent@example.com",
            password="AgentPass123!",
            role=User.ROLE_AGENT,
        )

        response = self.client.get("/api/agents/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {user["id"] for user in response.data},
            {agent.id},
        )

        response = self.client.post(
            "/api/agents/",
            {
                "username": "attempted-admin",
                "email": "attempted-admin@example.com",
                "role": User.ROLE_ADMIN,
                "password": "AgentPass123!",
            },
            format="json",
            **self._csrf_headers(),
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            User.objects.get(username="attempted-admin").role,
            User.ROLE_AGENT,
        )

        response = self.client.delete(
            f"/api/agents/{self.admin.id}/",
            **self._csrf_headers(),
        )
        self.assertEqual(response.status_code, 404)

    def test_agent_cannot_manage_agent_accounts(self):
        agent = User.objects.create_user(
            username="restricted-agent",
            email="restricted-agent@example.com",
            password="AgentPass123!",
            role=User.ROLE_AGENT,
        )
        self.client.force_login(agent)

        response = self.client.get("/api/agents/")
        self.assertEqual(response.status_code, 403)

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
