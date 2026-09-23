from django.contrib.auth import authenticate, login, logout
from rest_framework import status, views, response
from .serializers import UserSerializer
from .models import User
from .permissions import IsAdmin, IsAgent

class LoginView(views.APIView):
    """Log in a user using Django's ``authenticate`` and ``login``.
    Expects ``username`` and ``password`` in the request data.
    Returns the serialized user on success.
    """
    permission_classes = []  # allow any

    def post(self, request, *args, **kwargs):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(request, username=username, password=password)
        if user is None:
            return response.Response({"detail": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)
        login(request, user)
        serializer = UserSerializer(user)
        return response.Response(serializer.data)

class LogoutView(views.APIView):
    """Log out the current user, clearing the session."""
    def post(self, request, *args, **kwargs):
        logout(request)
        return response.Response(status=status.HTTP_200_OK)

class MeView(views.APIView):
    """Return the current authenticated user.
    Returns 401 if no user is logged in.
    """
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return response.Response({"detail": "Authentication credentials were not provided."}, status=status.HTTP_401_UNAUTHORIZED)
        serializer = UserSerializer(request.user)
        return response.Response(serializer.data)

# Admin‑only user (agent) management viewset
from rest_framework import viewsets
from .permissions import IsAdmin

class AgentViewSet(viewsets.ModelViewSet):
    """CRUD operations for user accounts (agents). Only ADMIN role can access.
    The ``role`` field controls whether a user is ADMIN or AGENT.
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAdmin]
