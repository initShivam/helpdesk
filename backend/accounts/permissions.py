from rest_framework import permissions
from .models import User

class IsAdmin(permissions.BasePermission):
    """Allow access only to users with ADMIN role."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and getattr(request.user, 'is_admin', lambda: False)())

class IsAgent(permissions.BasePermission):
    """Allow access only to users with AGENT role."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and getattr(request.user, 'is_agent', lambda: False)())
