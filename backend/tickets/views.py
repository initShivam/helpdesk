from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.http import FileResponse
from django.utils.text import get_valid_filename
from email_ingestion.models import EmailAttachment
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.exceptions import NotAuthenticated
from .models import Ticket, TicketMessage
from .serializers import TicketSerializer, TicketMessageSerializer
from .auth import SessionAuthenticationWith401
from .ai import enrich_ticket
from .models import AILog
from .tasks import generate_ai_suggestion

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
        enrich_ticket(ticket, ticket.description or '')

    @action(detail=True, methods=["post"], url_path="suggest-reply")
    def suggest_reply(self, request, pk=None):
        ticket = self.get_object()
        task = generate_ai_suggestion.delay(ticket.pk)
        return Response({"task_id": task.id}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["get"], url_path="suggestion-status")
    def suggestion_status(self, request, pk=None):
        ticket = self.get_object()
        log = ticket.ai_logs.filter(operation="suggest_reply").order_by("-created_at").first()
        if not log:
            return Response({"status": "not_started"})
        message = log.messages.order_by("-created_at").first()
        return Response(
            {
                "id": log.id,
                "status": log.status,
                "error_message": log.error_message,
                "message": TicketMessageSerializer(message).data if message else None,
            }
        )

    @action(detail=True, methods=["post"], url_path="accept-suggestion")
    def accept_suggestion(self, request, pk=None):
        ticket = self.get_object()
        message_id = request.data.get("message_id")
        message = ticket.messages.filter(
            pk=message_id, is_ai_generated=True, is_draft=True
        ).first()
        if not message:
            return Response({"detail": "AI draft not found."}, status=status.HTTP_404_NOT_FOUND)
        message.body = str(request.data.get("body", message.body)).strip()
        if not message.body:
            return Response({"detail": "Reply cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)
        message.is_ai_generated = False
        message.is_draft = False
        message.sender = request.user
        message.save(update_fields=["body", "is_ai_generated", "is_draft", "sender", "updated_at"])
        return Response(TicketMessageSerializer(message).data)

    @action(detail=True, methods=["get"], url_path=r"attachments/(?P<attachment_pk>[0-9]+)")
    def download_attachment(self, request, pk=None, attachment_pk=None):
        attachment = get_object_or_404(
            EmailAttachment,
            pk=attachment_pk,
            inbound_email__ticket_id=pk,
        )
        if not attachment.file:
            return Response({"detail": "Attachment file is unavailable."}, status=status.HTTP_404_NOT_FOUND)
        return FileResponse(
            attachment.file.open("rb"),
            as_attachment=True,
            filename=get_valid_filename(attachment.filename),
            content_type=attachment.content_type or "application/octet-stream",
        )

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
