from accounts.models import Team, User


class TicketRoutingService:
    """Provide tenant-scoped candidates for future category-based ticket routing."""

    @staticmethod
    def eligible_agents(team: Team):
        if team.organization_id != team.department.organization_id:
            return User.objects.none()
        return (
            User.objects.filter(
                organization_id=team.organization_id,
                department_id=team.department_id,
                role=User.ROLE_AGENT,
                is_active=True,
                team_memberships__team=team,
                team_memberships__is_active=True,
            )
            .order_by("last_name", "first_name", "username")
            .distinct()
        )
