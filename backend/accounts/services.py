from django.db import transaction
from django.utils.text import slugify

from .models import Department, Organization, Team, User, ensure_default_team


DEFAULT_DEPARTMENTS = (
    "Customer Support",
    "Technical Support",
    "Billing & Payments",
    "Sales",
    "Customer Success",
    "Product Support",
    "Account & Security",
)


@transaction.atomic
def create_organization(*, name: str, owner: User, slug: str = "") -> Organization:
    if owner.role != User.ROLE_ADMIN and not owner.is_superuser:
        raise ValueError("Organization owner must be an administrator.")

    previous_organization = owner.organization if owner.organization_id else None
    organization = Organization.objects.create(
        name=name.strip(),
        slug=slug.strip() or slugify(name),
        owner=owner,
    )
    if previous_organization and previous_organization.owner_id == owner.pk:
        previous_organization.owner = None
        previous_organization.save(update_fields=["owner", "updated_at"])
    owner.organization = organization
    owner.save(update_fields=["organization"])
    create_default_departments(organization)
    return organization


@transaction.atomic
def create_default_departments(organization: Organization) -> None:
    for name in DEFAULT_DEPARTMENTS:
        department, _ = Department.objects.get_or_create(
            organization=organization,
            name=name,
        )
        ensure_default_team(department)


@transaction.atomic
def create_department(*, organization: Organization, name: str, description: str = "") -> Department:
    department = Department.objects.create(
        organization=organization,
        name=name.strip(),
        description=description.strip(),
    )
    ensure_default_team(department)
    return department


@transaction.atomic
def update_department(department: Department, *, name: str, description: str) -> Department:
    old_default_name = f"{department.name} Team"
    department.name = name.strip()
    department.description = description.strip()
    department.save(update_fields=["name", "description", "updated_at"])
    default_team = Team.objects.filter(department=department, is_default=True).first()
    if default_team and default_team.name == old_default_name:
        default_team.name = f"{department.name} Team"
        default_team.save(update_fields=["name", "updated_at"])
    return department
