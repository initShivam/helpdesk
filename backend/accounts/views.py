from django.contrib.auth import authenticate, login, logout
from django.conf import settings
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from knox.models import AuthToken
from rest_framework import response, status, views, viewsets
from rest_framework.throttling import ScopedRateThrottle

from .models import User
from .permissions import IsAdmin
from .serializers import UserSerializer


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

    def perform_create(self, serializer):
        serializer.save(role=User.ROLE_AGENT)

    def perform_update(self, serializer):
        serializer.save(role=User.ROLE_AGENT)
