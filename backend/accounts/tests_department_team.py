from django.test import TestCase
from rest_framework.test import APIClient

from .models import (
    Department,
    Organization,
    Team,
    TeamMember,
    User,
    ensure_default_team,
)
from .services import DEFAULT_DEPARTMENTS, create_organization
from tickets.routing import TicketRoutingService


class DepartmentTeamManagementTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.get(slug="default-organization")
        self.admin = User.objects.create_user(
            username="department-admin",
            email="department-admin@example.com",
            password="AdminPass123!",
            role=User.ROLE_ADMIN,
            organization=self.organization,
        )
        self.client = APIClient()
        self.client.force_login(self.admin)

    def create_department(self, name):
        response = self.client.post(
            "/api/departments/",
            {"name": name},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return Department.objects.get(pk=response.data["id"])

    def create_agent(self, username, department):
        response = self.client.post(
            "/api/agents/",
            {
                "username": username,
                "email": f"{username}@example.com",
                "password": "AgentPass123!",
                "role": User.ROLE_AGENT,
                "department_id": department.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return User.objects.get(pk=response.data["id"])

    def test_department_creation_creates_default_team_and_hides_tenant_id(self):
        department = self.create_department("API Support")

        team = Team.objects.get(department=department, is_default=True)
        self.assertEqual(team.organization, self.organization)
        self.assertEqual(team.name, "API Support Team")
        self.assertNotIn("organization_id", self.client.get(
            f"/api/departments/{department.pk}/",
        ).data)

    def test_agent_creation_and_department_change_sync_default_team_membership(self):
        technical = self.create_department("Technical Operations")
        billing = self.create_department("Billing Operations")
        first_agent = self.create_agent("first-agent", technical)
        second_agent = self.create_agent("second-agent", technical)
        technical_team = Team.objects.get(department=technical, is_default=True)

        self.assertEqual(
            set(
                TeamMember.objects.filter(
                    agent__in=[first_agent, second_agent],
                    team=technical_team,
                    is_active=True,
                ).values_list("agent_id", flat=True)
            ),
            {first_agent.pk, second_agent.pk},
        )

        response = self.client.patch(
            f"/api/agents/{first_agent.pk}/",
            {"department_id": billing.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        first_agent.refresh_from_db()
        billing_team = Team.objects.get(department=billing, is_default=True)

        self.assertEqual(first_agent.department, billing)
        self.assertFalse(
            TeamMember.objects.get(agent=first_agent, team=technical_team).is_active
        )
        self.assertTrue(
            TeamMember.objects.get(agent=first_agent, team=billing_team).is_active
        )
        self.assertTrue(
            TeamMember.objects.get(agent=second_agent, team=technical_team).is_active
        )
        self.assertEqual(
            list(TicketRoutingService.eligible_agents(technical_team)),
            [second_agent],
        )

    def test_agents_cannot_read_or_manage_other_organizations(self):
        other_organization = Organization.objects.create(
            name="Other Organization",
            slug="other-organization",
        )
        other_admin = User.objects.create_user(
            username="other-admin",
            email="other-admin@example.com",
            password="AdminPass123!",
            role=User.ROLE_ADMIN,
            organization=other_organization,
        )
        other_department = Department.objects.create(
            organization=other_organization,
            name="Private Support",
        )
        ensure_default_team(other_department)
        other_agent = User.objects.create_user(
            username="other-agent",
            email="other-agent@example.com",
            password="AgentPass123!",
            role=User.ROLE_AGENT,
            organization=other_organization,
            department=other_department,
        )
        team = Team.objects.get(department=other_department, is_default=True)
        TeamMember.objects.create(team=team, agent=other_agent)

        departments = self.client.get("/api/departments/")
        teams = self.client.get(f"/api/teams/{team.pk}/")
        agents = self.client.get("/api/agents/")

        self.assertEqual(departments.status_code, 200)
        self.assertNotIn(other_department.pk, {item["id"] for item in departments.data})
        self.assertEqual(teams.status_code, 404)
        self.assertNotIn(other_agent.pk, {item["id"] for item in agents.data})

    def test_agent_can_view_own_department_and_team_but_cannot_manage_them(self):
        department = self.create_department("Success Escalations")
        agent = self.create_agent("limited-agent", department)
        self.client.force_login(agent)

        departments = self.client.get("/api/departments/")
        team = Team.objects.get(department=department, is_default=True)
        members = self.client.get(f"/api/teams/{team.pk}/members/")
        create_department = self.client.post(
            "/api/departments/",
            {"name": "Forbidden"},
            format="json",
        )

        self.assertEqual([item["id"] for item in departments.data], [department.pk])
        self.assertEqual(members.status_code, 200)
        self.assertEqual(members.data[0]["agent_id"], agent.pk)
        self.assertEqual(create_department.status_code, 403)

    def test_department_delete_deactivates_instead_of_deleting(self):
        department = self.create_department("Product Engineering")

        response = self.client.delete(f"/api/departments/{department.pk}/")

        self.assertEqual(response.status_code, 204)
        department.refresh_from_db()
        self.assertFalse(department.is_active)
        self.assertTrue(Team.objects.filter(department=department).exists())

    def test_new_organization_creation_assigns_owner_and_seeds_departments(self):
        owner = User.objects.create_user(
            username="new-org-owner",
            email="new-org-owner@example.com",
            password="AdminPass123!",
            role=User.ROLE_ADMIN,
            organization=self.organization,
        )

        organization = create_organization(name="Product Company", owner=owner)

        owner.refresh_from_db()
        self.assertEqual(owner.organization, organization)
        self.assertEqual(organization.owner, owner)
        self.assertEqual(
            set(organization.departments.values_list("name", flat=True)),
            set(DEFAULT_DEPARTMENTS),
        )
        self.assertEqual(organization.teams.filter(is_default=True).count(), len(DEFAULT_DEPARTMENTS))
