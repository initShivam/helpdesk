from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def assign_bootstrap_organization(apps, schema_editor):
    Organization = apps.get_model("accounts", "Organization")
    User = apps.get_model("accounts", "User")
    organization, _ = Organization.objects.using(schema_editor.connection.alias).get_or_create(
        slug="default-organization",
        defaults={"name": "Default Organization"},
    )
    users = User.objects.using(schema_editor.connection.alias)
    owner = users.filter(is_superuser=True).order_by("id").first()
    if owner is None:
        owner = users.filter(role="ADMIN").order_by("id").first()
    if owner:
        owner.role = "ADMIN"
        owner.save(using=schema_editor.connection.alias, update_fields=["role"])
        organization.owner_id = owner.pk
        organization.save(using=schema_editor.connection.alias, update_fields=["owner"])
    users.update(organization_id=organization.pk)


def unassign_bootstrap_organization(apps, schema_editor):
    Organization = apps.get_model("accounts", "Organization")
    User = apps.get_model("accounts", "User")
    database = schema_editor.connection.alias
    organization = Organization.objects.using(database).filter(
        slug="default-organization",
    ).first()
    if organization:
        User.objects.using(database).filter(
            organization_id=organization.pk,
        ).update(organization_id=None)
        organization.owner_id = None
        organization.save(using=database, update_fields=["owner"])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_user_department"),
    ]

    operations = [
        migrations.CreateModel(
            name="Organization",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=150)),
                ("slug", models.SlugField(max_length=160, unique=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="owned_organizations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="user",
            name="organization",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="users",
                to="accounts.organization",
            ),
        ),
        migrations.RunPython(
            assign_bootstrap_organization,
            unassign_bootstrap_organization,
        ),
        migrations.AlterField(
            model_name="user",
            name="organization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="users",
                to="accounts.organization",
            ),
        ),
    ]
