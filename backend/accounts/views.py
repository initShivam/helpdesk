from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import response, status, views, viewsets

from .models import User
from .permissions import IsAdmin
from .serializers import UserSerializer


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

    def post(self, request, *args, **kwargs):
        identifier = request.data.get("username") or request.data.get("email")
        password = request.data.get("password")
        if (
            not isinstance(identifier, str)
            or not identifier.strip()
            or not isinstance(password, str)
            or not password
        ):
            return response.Response(
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
            return response.Response(
                {"detail": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        login(request, user)
        return response.Response(UserSerializer(user).data)


class LogoutView(views.APIView):
    """Log out the current user, clearing the session."""

    def post(self, request, *args, **kwargs):
        logout(request)
        return response.Response(status=status.HTTP_200_OK)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class MeView(views.APIView):
    """Return the current authenticated user and ensure a CSRF cookie exists."""

    authentication_classes = []

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return response.Response(
                {"detail": "Authentication credentials were not provided."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return response.Response(UserSerializer(request.user).data)


class AgentViewSet(viewsets.ModelViewSet):
    """CRUD operations for user accounts, restricted to administrators."""

    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAdmin]
