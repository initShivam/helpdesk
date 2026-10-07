from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers

from .models import (
    Department,
    Team,
    TeamMember,
    User,
    sync_agent_team_membership,
)
from .services import create_department, update_department


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=8)
    department = serializers.CharField(
        source="department.name",
        read_only=True,
        allow_null=True,
    )
    department_id = serializers.PrimaryKeyRelatedField(
        source="department",
        queryset=Department.objects.all(),
        required=False,
        allow_null=True,
    )
    team = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "department",
            "department_id",
            "team",
            "role",
            "is_active",
            "password",
        ]
        read_only_fields = ["id", "department", "team"]

    def to_internal_value(self, data):
        if "organization_id" in data or "organization" in data:
            raise serializers.ValidationError(
                {"organization_id": "Organization is determined by your authenticated account."}
            )
        return super().to_internal_value(data)

    def validate_department_id(self, department):
        request = self.context.get("request")
        organization_id = getattr(getattr(request, "user", None), "organization_id", None)
        if department and department.organization_id != organization_id:
            raise serializers.ValidationError(
                "Choose a department belonging to your organization."
            )
        if department and not department.is_active:
            raise serializers.ValidationError("Choose an active department.")
        return department

    def validate_password(self, value):
        validate_password(value, self.instance)
        return value

    def get_team(self, user):
        membership = (
            user.team_memberships.filter(
                is_active=True,
                team__is_default=True,
                team__is_active=True,
            )
            .select_related("team")
            .first()
        )
        return (
            {"id": membership.team_id, "name": membership.team.name}
            if membership
            else None
        )

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        if not password:
            raise serializers.ValidationError(
                {"password": "This field is required when creating a user."}
            )
        request = self.context.get("request")
        organization = getattr(getattr(request, "user", None), "organization", None)
        if organization is None:
            raise serializers.ValidationError(
                {"detail": "Your account is not associated with an organization."}
            )

        with transaction.atomic():
            user = User.objects.create_user(
                password=password,
                organization=organization,
                **validated_data,
            )
            if user.role == User.ROLE_AGENT:
                sync_agent_team_membership(user, user.department)
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        if "organization" in validated_data:
            raise serializers.ValidationError(
                {"organization_id": "Organization cannot be changed through agent management."}
            )
        with transaction.atomic():
            user = super().update(instance, validated_data)
            if password:
                user.set_password(password)
                user.save(update_fields=["password"])
            if user.role == User.ROLE_AGENT:
                sync_agent_team_membership(user, user.department)
        return user


class DepartmentSerializer(serializers.ModelSerializer):
    agents_count = serializers.SerializerMethodField()
    default_team = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = [
            "id",
            "name",
            "description",
            "is_active",
            "agents_count",
            "default_team",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "agents_count",
            "default_team",
            "created_at",
            "updated_at",
        ]

    def validate_name(self, value):
        organization_id = self.context["request"].user.organization_id
        departments = Department.objects.filter(
            organization_id=organization_id,
            name=value.strip(),
        )
        if self.instance:
            departments = departments.exclude(pk=self.instance.pk)
        if departments.exists():
            raise serializers.ValidationError(
                "A department with this name already exists in your organization."
            )
        return value.strip()

    def get_agents_count(self, department):
        return department.agents.filter(role=User.ROLE_AGENT).count()

    def get_default_team(self, department):
        team = department.teams.filter(is_default=True).first()
        return {"id": team.pk, "name": team.name} if team else None

    def create(self, validated_data):
        return create_department(
            organization=self.context["request"].user.organization,
            name=validated_data["name"],
            description=validated_data.get("description", ""),
        )

    def update(self, instance, validated_data):
        name = validated_data.pop("name", instance.name)
        description = validated_data.pop("description", instance.description)
        is_active = validated_data.pop("is_active", instance.is_active)
        instance = update_department(
            instance,
            name=name,
            description=description,
        )
        instance.is_active = is_active
        instance.save(update_fields=["is_active", "updated_at"])
        instance.teams.filter(is_default=True).update(is_active=is_active)
        return instance


class TeamSerializer(serializers.ModelSerializer):
    department_id = serializers.PrimaryKeyRelatedField(
        source="department",
        queryset=Department.objects.all(),
    )
    department_name = serializers.CharField(source="department.name", read_only=True)
    members_count = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = [
            "id",
            "name",
            "description",
            "department_id",
            "department_name",
            "is_default",
            "is_active",
            "members_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "department_name",
            "is_default",
            "members_count",
            "created_at",
            "updated_at",
        ]

    def validate_department_id(self, department):
        request = self.context.get("request")
        organization_id = getattr(getattr(request, "user", None), "organization_id", None)
        if department.organization_id != organization_id:
            raise serializers.ValidationError(
                "Choose a department belonging to your organization."
            )
        if not department.is_active:
            raise serializers.ValidationError("Teams can only be added to active departments.")
        return department

    def validate(self, attrs):
        department = attrs.get("department", getattr(self.instance, "department", None))
        request = self.context.get("request")
        organization_id = getattr(getattr(request, "user", None), "organization_id", None)
        if department and department.organization_id != organization_id:
            raise serializers.ValidationError(
                {"department_id": "Choose a department belonging to your organization."}
            )
        name = attrs.get("name", getattr(self.instance, "name", ""))
        if department and name:
            teams = Team.objects.filter(
                organization_id=organization_id,
                department=department,
                name=name.strip(),
            )
            if self.instance:
                teams = teams.exclude(pk=self.instance.pk)
            if teams.exists():
                raise serializers.ValidationError(
                    {"name": "A team with this name already exists in the selected department."}
                )
        return attrs

    def get_members_count(self, team):
        return team.memberships.filter(is_active=True).count()

    def create(self, validated_data):
        request = self.context["request"]
        return Team.objects.create(
            organization=request.user.organization,
            **validated_data,
        )


class TeamMemberSerializer(serializers.ModelSerializer):
    agent_id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(source="agent.username", read_only=True)
    first_name = serializers.CharField(source="agent.first_name", read_only=True)
    last_name = serializers.CharField(source="agent.last_name", read_only=True)
    email = serializers.EmailField(source="agent.email", read_only=True)

    class Meta:
        model = TeamMember
        fields = [
            "agent_id",
            "username",
            "first_name",
            "last_name",
            "email",
            "joined_at",
            "is_active",
        ]
