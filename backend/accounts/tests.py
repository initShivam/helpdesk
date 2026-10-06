from datetime import timedelta

from django.utils import timezone
from django.test import TestCase
from knox.models import AuthToken
from rest_framework.test import APIClient

from tickets.models import Ticket, TicketMessage

from .models import AuditLog, User


class AuthenticationAndUserManagementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="adminpass",
            role=User.ROLE_ADMIN,
        )
        self.client = APIClient(enforce_csrf_checks=True)

    def _create_agent(self):
        return User.objects.create_user(
            username="agent",
            email="agent@example.com",
            password="agentpass",
            role=User.ROLE_AGENT,
        )

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

    def test_token_login_returns_an_expiring_token_without_a_session_cookie(self):
        csrf_token = self.client.get("/api/auth/csrf/").data["csrfToken"]
        response = self.client.post(
            "/api/auth/token-login/",
            {"username": "admin", "password": "adminpass"},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["token"])
        self.assertEqual(response.data["user"]["id"], self.admin.id)
        self.assertEqual(response.data["user"]["role"], User.ROLE_ADMIN)
        self.assertNotIn("sessionid", self.client.cookies)
        auth_token = AuthToken.objects.get(user=self.admin)
        self.assertGreater(auth_token.expiry, timezone.now())
        self.assertLessEqual(
            auth_token.expiry,
            timezone.now() + timedelta(minutes=31),
        )

    def test_token_login_requires_csrf_and_rejects_invalid_credentials(self):
        response = self.client.post(
            "/api/auth/token-login/",
            {"username": "admin", "password": "adminpass"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

        csrf_token = self.client.get("/api/auth/csrf/").data["csrfToken"]
        response = self.client.post(
            "/api/auth/token-login/",
            {"username": "admin", "password": "incorrect"},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(AuthToken.objects.count(), 0)

    def test_valid_token_authenticates_and_invalid_bearer_returns_401(self):
        _, token = AuthToken.objects.create(user=self.admin)
        client = APIClient()
        response = client.get("/api/auth/me/", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], self.admin.id)

        client.force_login(self._create_agent())
        response = client.get("/api/auth/me/", HTTP_AUTHORIZATION="Bearer invalid-token")
        self.assertEqual(response.status_code, 401)

    def test_bearer_identity_overrides_a_different_shared_session(self):
        agent = self._create_agent()
        _, admin_token = AuthToken.objects.create(user=self.admin)
        client = APIClient()
        client.force_login(agent)

        response = client.get(
            "/api/auth/me/",
            HTTP_AUTHORIZATION=f"Bearer {admin_token}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], self.admin.id)

    def test_expired_token_returns_401(self):
        auth_token, token = AuthToken.objects.create(user=self.admin)
        auth_token.expiry = timezone.now() - timedelta(seconds=1)
        auth_token.save(update_fields=["expiry"])

        response = APIClient().get(
            "/api/auth/me/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 401)

    def test_token_logout_revokes_only_the_current_token(self):
        _, admin_token = AuthToken.objects.create(user=self.admin)
        agent = self._create_agent()
        _, agent_token = AuthToken.objects.create(user=agent)
        admin_client = APIClient()
        agent_client = APIClient()

        response = admin_client.post(
            "/api/auth/logout/",
            HTTP_AUTHORIZATION=f"Bearer {admin_token}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            admin_client.get(
                "/api/auth/me/",
                HTTP_AUTHORIZATION=f"Bearer {admin_token}",
            ).status_code,
            401,
        )
        self.assertEqual(
            agent_client.get(
                "/api/auth/me/",
                HTTP_AUTHORIZATION=f"Bearer {agent_token}",
            ).status_code,
            200,
        )

    def test_token_authentication_preserves_server_side_role_permissions(self):
        _, admin_token = AuthToken.objects.create(user=self.admin)
        agent = self._create_agent()
        _, agent_token = AuthToken.objects.create(user=agent)

        admin_response = APIClient().get(
            "/api/agents/",
            HTTP_AUTHORIZATION=f"Bearer {admin_token}",
        )
        agent_response = APIClient().get(
            "/api/agents/",
            HTTP_AUTHORIZATION=f"Bearer {agent_token}",
        )
        self.assertEqual(admin_response.status_code, 200)
        self.assertEqual(agent_response.status_code, 403)

    def test_two_tokens_authenticate_as_independent_users(self):
        _, admin_token = AuthToken.objects.create(user=self.admin)
        agent = self._create_agent()
        _, agent_token = AuthToken.objects.create(user=agent)

        admin_response = APIClient().get(
            "/api/auth/me/",
            HTTP_AUTHORIZATION=f"Bearer {admin_token}",
        )
        agent_response = APIClient().get(
            "/api/auth/me/",
            HTTP_AUTHORIZATION=f"Bearer {agent_token}",
        )

        self.assertEqual(admin_response.data["role"], User.ROLE_ADMIN)
        self.assertEqual(agent_response.data["role"], User.ROLE_AGENT)

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

    def test_login_and_logout_are_audited_at_the_auth_routes(self):
        csrf_token = self.client.get("/api/auth/csrf/").data["csrfToken"]
        self.client.post(
            "/api/auth/login/",
            {"username": "admin", "password": "adminpass"},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertTrue(AuditLog.objects.filter(user=self.admin, action="Login").exists())

        csrf_token = self.client.get("/api/auth/csrf/").data["csrfToken"]
        self.client.post(
            "/api/auth/logout/",
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertTrue(AuditLog.objects.filter(user=self.admin, action="Logout").exists())

    def test_ticket_status_and_ai_acceptance_are_audited(self):
        self.client.force_login(self.admin)
        ticket = Ticket.objects.create(
            ticket_number="AUDIT-001",
            subject="Audit events",
            requester_email="customer@example.com",
        )
        csrf_token = self.client.get("/api/auth/csrf/").data["csrfToken"]
        response = self.client.patch(
            f"/api/tickets/{ticket.pk}/",
            {"status": "resolved"},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(response.status_code, 200)

        draft = TicketMessage.objects.create(
            ticket=ticket,
            body="Suggested response",
            message_type="agent",
            is_ai_generated=True,
            is_draft=True,
        )
        response = self.client.post(
            f"/api/tickets/{ticket.pk}/accept-suggestion/",
            {"message_id": draft.pk, "body": draft.body},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            AuditLog.objects.filter(user=self.admin, action="Ticket Status Change").exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(user=self.admin, action="AI Suggestion Accepted").exists()
        )

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
