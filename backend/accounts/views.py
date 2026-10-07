from django.contrib.auth import authenticate, login, logout
from django.conf import settings
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from knox.models import AuthToken
from rest_framework import permissions, response, status, views, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.throttling import ScopedRateThrottle

from .models import Department, Team, TeamMember, User
from .permissions import IsAdmin
from .serializers import (
    DepartmentSerializer,
    TeamMemberSerializer,
    TeamSerializer,
    UserSerializer,
)


def _authenticate_credentials(request):
    identifier = request.data.get("username") or request.data.get("email")
    password = request.data.get("password")
    if (
        not isinstance(identifier, str)
        or not identifier.strip()
        or not isinstance(password, str)
        or not password
    ):
        return None, response.Response(
            {"detail": "Username/email and password are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    identifier = identifier.strip()
    user = authenticate(request, username=identifier, password=password)
    if user is None:
        email_user = User.objects.filter(email__iexact=identifier).first()
        if email_user:
            user = authenticate(
                request,
                username=email_user.get_username(),
                password=password,
            )
    if user is None:
        return None, response.Response(
            {"detail": "Invalid credentials"},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    return user, None


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfTokenView(views.APIView):
    """Issue a CSRF cookie and return its token for cross-origin clients."""

    permission_classes = []
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        return response.Response({"csrfToken": get_token(request)})


@method_decorator(csrf_protect, name="dispatch")
class LoginView(views.APIView):
    """Authenticate a user by username or email and create a session."""

    permission_classes = []
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle] if settings.IS_PRODUCTION else []
    throttle_scope = "login"

    def post(self, request, *args, **kwargs):
        user, error = _authenticate_credentials(request)
        if error:
            return error

        login(request, user)
        return response.Response(UserSerializer(user).data)


@method_decorator(csrf_protect, name="dispatch")
class TokenLoginView(views.APIView):
    """Authenticate a user and issue an expiring, independently revocable token."""

    permission_classes = []
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle] if settings.IS_PRODUCTION else []
    throttle_scope = "login"

    def post(self, request, *args, **kwargs):
        user, error = _authenticate_credentials(request)
        if error:
            return error

        request._request.audit_user = user
        _, token = AuthToken.objects.create(user=user)
        return response.Response({
            "token": token,
            "user": UserSerializer(user).data,
        })


class LogoutView(views.APIView):
    """Revoke this token or end the current legacy Django session."""

    def post(self, request, *args, **kwargs):
        request._request.audit_user = request.user
        if isinstance(request.auth, AuthToken):
            request.auth.delete()
        else:
            logout(request)
        return response.Response(status=status.HTTP_200_OK)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class MeView(views.APIView):
    """Return the current authenticated user and ensure a CSRF cookie exists."""

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return response.Response(
                {"detail": "Authentication credentials were not provided."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return response.Response(UserSerializer(request.user).data)


class AgentViewSet(viewsets.ModelViewSet):
    """CRUD operations for user accounts, restricted to administrators."""

    queryset = User.objects.filter(role=User.ROLE_AGENT)
    serializer_class = UserSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(organization_id=self.request.user.organization_id)
            .select_related("department")
            .prefetch_related("team_memberships__team")
        )

    def perform_create(self, serializer):
        serializer.save(role=User.ROLE_AGENT)

    def perform_update(self, serializer):
        serializer.save(role=User.ROLE_AGENT)


class IsAdminOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.method in permissions.SAFE_METHODS or request.user.is_admin()


class DepartmentViewSet(viewsets.ModelViewSet):
    serializer_class = DepartmentSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        queryset = Department.objects.filter(
            organization_id=self.request.user.organization_id,
        ).prefetch_related("agents", "teams")
        if not self.request.user.is_admin():
            queryset = queryset.filter(
                is_active=True,
                agents=self.request.user,
            )
        return queryset.distinct()

    def perform_create(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        instance.teams.filter(is_default=True).update(is_active=False)


class TeamViewSet(viewsets.ModelViewSet):
    serializer_class = TeamSerializer
    permission_classes = [IsAdminOrReadOnly]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        queryset = Team.objects.filter(
            organization_id=self.request.user.organization_id,
        ).select_related("department")
        if not self.request.user.is_admin():
            queryset = queryset.filter(
                is_active=True,
                memberships__agent=self.request.user,
                memberships__is_active=True,
            )
        department_id = self.request.query_params.get("department_id")
        if department_id:
            queryset = queryset.filter(department_id=department_id)
        return queryset.distinct()

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=True, methods=["get"], url_path="members")
    def members(self, request, pk=None):
        team = self.get_object()
        if not request.user.is_admin() and not TeamMember.objects.filter(
            team=team,
            agent=request.user,
            is_active=True,
        ).exists():
            raise PermissionDenied("You cannot view members of this team.")
        members = (
            TeamMember.objects.filter(team=team, is_active=True)
            .select_related("agent")
            .order_by("agent__last_name", "agent__first_name", "agent__username")
        )
        return response.Response(TeamMemberSerializer(members, many=True).data)
