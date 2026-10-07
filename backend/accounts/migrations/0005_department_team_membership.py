from django.conf import settings
from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion


DEFAULT_DEPARTMENTS = (
    "Customer Support",
    "Technical Support",
    "Billing & Payments",
    "Sales",
    "Customer Success",
    "Product Support",
    "Account & Security",
)


def seed_departments_and_migrate_users(apps, schema_editor):
    Department = apps.get_model("accounts", "Department")
    Team = apps.get_model("accounts", "Team")
    TeamMember = apps.get_model("accounts", "TeamMember")
    Organization = apps.get_model("accounts", "Organization")
    User = apps.get_model("accounts", "User")
    database = schema_editor.connection.alias

    def department_for(organization, name):
        department, _ = Department.objects.using(database).get_or_create(
            organization_id=organization.pk,
            name=name,
        )
        Team.objects.using(database).get_or_create(
            department_id=department.pk,
            is_default=True,
            defaults={
                "organization_id": organization.pk,
                "name": f"{name} Team",
            },
        )
        return department

    for organization in Organization.objects.using(database).all().iterator():
        for name in DEFAULT_DEPARTMENTS:
            department_for(organization, name)

    for user in User.objects.using(database).all().iterator():
        legacy_name = (user.department_name or "").strip()
        if not legacy_name:
            continue
        department = department_for(
            Organization.objects.using(database).get(pk=user.organization_id),
            legacy_name,
        )
        user.department_id = department.pk
        user.save(using=database, update_fields=["department"])
        if user.role == "AGENT":
            default_team = Team.objects.using(database).get(
                department_id=department.pk,
                is_default=True,
            )
            TeamMember.objects.using(database).get_or_create(
                team_id=default_team.pk,
                agent_id=user.pk,
            )


def restore_legacy_department_names(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    database = schema_editor.connection.alias
    for user in User.objects.using(database).select_related("department").iterator():
        user.department_name = user.department.name if user.department_id else ""
        user.save(using=database, update_fields=["department_name"])


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0004_organization"),
    ]

    operations = [
        migrations.RenameField(
            model_name="user",
            old_name="department",
            new_name="department_name",
        ),
        migrations.CreateModel(
            name="Department",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="departments",
                        to="accounts.organization",
                    ),
                ),
            ],
            options={
                "ordering": ["name", "id"],
            },
        ),
        migrations.CreateModel(
            name="Team",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("description", models.TextField(blank=True)),
                ("is_default", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "department",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="teams",
                        to="accounts.department",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="teams",
                        to="accounts.organization",
                    ),
                ),
            ],
            options={
                "ordering": ["department__name", "name", "id"],
            },
        ),
        migrations.CreateModel(
            name="TeamMember",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("joined_at", models.DateTimeField(auto_now_add=True)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "agent",
                    models.ForeignKey(
                        limit_choices_to={"role": "AGENT"},
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="team_memberships",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "team",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to="accounts.team",
                    ),
                ),
            ],
            options={
                "ordering": ["joined_at", "id"],
            },
        ),
        migrations.AddField(
            model_name="user",
            name="department",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="agents",
                to="accounts.department",
            ),
        ),
        migrations.AddConstraint(
            model_name="department",
            constraint=models.UniqueConstraint(
                fields=("organization", "name"),
                name="accounts_dept_org_name_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="team",
            constraint=models.UniqueConstraint(
                fields=("organization", "department", "name"),
                name="accounts_team_org_dept_name_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="team",
            constraint=models.UniqueConstraint(
                condition=Q(is_default=True),
                fields=("department",),
                name="accounts_one_default_team_per_dept",
            ),
        ),
        migrations.AddConstraint(
            model_name="teammember",
            constraint=models.UniqueConstraint(
                fields=("team", "agent"),
                name="accounts_team_member_uniq",
            ),
        ),
        migrations.RunPython(
            seed_departments_and_migrate_users,
            restore_legacy_department_names,
        ),
        migrations.AlterField(
            model_name="user",
            name="department_name",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.RunPython(
            migrations.RunPython.noop,
            restore_legacy_department_names,
        ),
        migrations.RemoveField(
            model_name="user",
            name="department_name",
        ),
    ]
