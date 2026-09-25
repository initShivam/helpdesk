from rest_framework import viewsets, permissions, filters
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.exceptions import NotAuthenticated
from .models import Ticket, TicketMessage
from .serializers import TicketSerializer, TicketMessageSerializer
from .auth import SessionAuthenticationWith401
from .ai import enrich_ticket

class TicketPermission(permissions.BasePermission):
    """Custom permission for TicketViewSet.
    * Unauthenticated → 401.
    * Agents can list, retrieve, create, update, partial_update.
    * Agents cannot DELETE.
    * Admins can perform any action, including DELETE.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            raise NotAuthenticated('Authentication credentials were not provided.')
        if request.method == "DELETE":
            return getattr(request.user, "role", "") == "ADMIN" or request.user.is_staff
        return getattr(request.user, "role", "") in ("ADMIN", "AGENT") or request.user.is_staff

class TicketMessagePermission(permissions.BasePermission):
    """Permission for TicketMessage viewset.
    * Unauthenticated → 401.
    * Agents and admins can list/retrieve.
    * Agents can create/update. Admins can create/update/delete.
    * Delete is admin‑only.
    """

    def has_permission(self, request, view):
        # Authentication is handled by SessionAuthenticationWith401 which raises 401 for unauthenticated requests.
        if not request.user or not request.user.is_authenticated:
            raise NotAuthenticated('Authentication credentials were not provided.')
        role = getattr(request.user, "role", "")
        if view.action in ["list", "retrieve"]:
            return role in ("ADMIN", "AGENT") or request.user.is_staff
        if view.action in ["create", "partial_update", "update"]:
            return role in ("ADMIN", "AGENT") or request.user.is_staff
        if view.action == "destroy":
            return role == "ADMIN" or request.user.is_staff
        return False

class TicketViewSet(viewsets.ModelViewSet):
    queryset = Ticket.objects.all()
    serializer_class = TicketSerializer
    permission_classes = [TicketPermission]
    authentication_classes = [SessionAuthenticationWith401]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["status", "category", "priority", "assigned_to"]
    search_fields = ["ticket_number", "subject", "requester_email"]
    ordering_fields = ["created_at", "updated_at"]
    ordering = ["-created_at"]

    def perform_create(self, serializer):
        ticket = serializer.save()
        enrich_ticket(ticket)

class TicketMessageViewSet(viewsets.ModelViewSet):
    serializer_class = TicketMessageSerializer
    permission_classes = [TicketMessagePermission]
    authentication_classes = [SessionAuthenticationWith401]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at", "updated_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        ticket_pk = self.kwargs.get("ticket_pk")
        # Ensure the parent ticket exists; raise 404 if not
        get_object_or_404(Ticket, pk=ticket_pk)
        return TicketMessage.objects.filter(ticket_id=ticket_pk)

    def perform_create(self, serializer):
        ticket_pk = self.kwargs.get("ticket_pk")
        serializer.save(ticket_id=ticket_pk)
