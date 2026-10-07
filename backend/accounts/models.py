from django.contrib.auth.models import AbstractUser
from django.db import models, transaction
from django.db.models import Q
from django.utils.text import slugify


class Organization(models.Model):
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160, unique=True)
    owner = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_organizations",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


def get_default_organization():
    organization, _ = Organization.objects.get_or_create(
        slug="default-organization",
        defaults={"name": "Default Organization"},
    )
    return organization


class User(AbstractUser):
    """Custom user model with role field for RBAC.

    Roles:
        ADMIN – can manage users and agents.
        AGENT – can work with tickets.
    """

    ROLE_ADMIN = 'ADMIN'
    ROLE_AGENT = 'AGENT'
    ROLE_CHOICES = [
        (ROLE_ADMIN, 'Admin'),
        (ROLE_AGENT, 'Agent'),
    ]

    role = models.CharField(max_length=5, choices=ROLE_CHOICES, default=ROLE_AGENT)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="users",
    )
    department = models.ForeignKey(
        "accounts.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agents",
    )

    # Override default ManyToMany fields to avoid reverse accessor name clashes
    groups = models.ManyToManyField(
        'auth.Group',
        related_name='custom_user_set',
        blank=True,
        help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.',
        verbose_name='groups',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='custom_user_set',
        blank=True,
        help_text='Specific permissions for this user.',
        verbose_name='user permissions',
    )

    def save(self, *args, **kwargs):
        if self.organization_id is None:
            self.organization = get_default_organization()
        super().save(*args, **kwargs)

    def is_admin(self):
        return self.role == self.ROLE_ADMIN or self.is_superuser

    def is_agent(self):
        return self.role == self.ROLE_AGENT


class Department(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="departments",
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="accounts_dept_org_name_uniq",
            )
        ]

    def __str__(self):
        return self.name


class Team(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="teams",
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name="teams",
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["department__name", "name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "department", "name"],
                name="accounts_team_org_dept_name_uniq",
            ),
            models.UniqueConstraint(
                fields=["department"],
                condition=Q(is_default=True),
                name="accounts_one_default_team_per_dept",
            ),
        ]

    def __str__(self):
        return self.name


class TeamMember(models.Model):
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    agent = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="team_memberships",
        limit_choices_to={"role": User.ROLE_AGENT},
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["joined_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "agent"],
                name="accounts_team_member_uniq",
            )
        ]

    def __str__(self):
        return f"{self.agent} - {self.team}"


def ensure_default_team(department):
    team, _ = Team.objects.get_or_create(
        department=department,
        is_default=True,
        defaults={
            "organization_id": department.organization_id,
            "name": f"{department.name} Team",
        },
    )
    return team


@transaction.atomic
def sync_agent_team_membership(agent, department):
    if department and department.organization_id != agent.organization_id:
        raise ValueError("Department must belong to the agent's organization.")
    team = ensure_default_team(department) if department else None
    memberships = TeamMember.objects.filter(agent=agent, is_active=True)
    if team:
        memberships.exclude(team=team).update(is_active=False)
    else:
        memberships.update(is_active=False)
    if not team:
        return None
    membership, _ = TeamMember.objects.update_or_create(
        team=team,
        agent=agent,
        defaults={"is_active": True},
    )
    return membership

class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=255)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.user} - {self.action} at {self.timestamp}"
