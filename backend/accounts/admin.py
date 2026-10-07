from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Department, Organization, Team, TeamMember, User
from .services import create_organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "owner", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug", "owner__username", "owner__email")
    readonly_fields = ("created_at", "updated_at")

    def get_field_queryset(self, db, db_field, request):
        if db_field.name == "owner":
            return User.objects.filter(role=User.ROLE_ADMIN).order_by("username")
        return super().get_field_queryset(db, db_field, request)

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        if not change:
            if obj.owner is None:
                raise ValidationError("Select an administrator to own the organization.")
            created = create_organization(
                name=obj.name,
                slug=obj.slug,
                owner=obj.owner,
            )
            obj.pk = created.pk
            obj.created_at = created.created_at
            obj.updated_at = created.updated_at
            return

        previous_owner_id = Organization.objects.get(pk=obj.pk).owner_id
        super().save_model(request, obj, form, change)
        if obj.owner_id and obj.owner_id != previous_owner_id:
            owner = User.objects.select_for_update().get(pk=obj.owner_id)
            owner.organization = obj
            owner.role = User.ROLE_ADMIN
            owner.save(update_fields=["organization", "role"])


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Helpdesk access", {"fields": ("role", "organization", "department")}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        (
            "Helpdesk access",
            {"fields": ("email", "first_name", "last_name", "role", "organization")},
        ),
    )
    list_display = DjangoUserAdmin.list_display + ("role", "organization", "department")
    list_filter = DjangoUserAdmin.list_filter + ("role", "organization")


admin.site.register(Department)
admin.site.register(Team)
admin.site.register(TeamMember)
