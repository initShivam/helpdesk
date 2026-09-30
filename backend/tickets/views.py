from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.conf import settings
from django.http import FileResponse
from django.utils.text import get_valid_filename
from email_ingestion.models import EmailAttachment
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.exceptions import NotAuthenticated
from rest_framework.throttling import ScopedRateThrottle
from datetime import timedelta
from django.utils import timezone
from rest_framework.views import APIView
from .models import Ticket, TicketMessage, AILog
from .serializers import TicketSerializer, TicketMessageSerializer
from .auth import SessionAuthenticationWith401
from .ai import enrich_ticket
from .tasks import generate_ai_suggestion, classify_ticket, summarize_ticket


def _enqueue_ai_task(task, ticket_id):
    """Queue AI work, surfacing task failures when local eager mode is enabled."""
    result = task.delay(ticket_id)
    if settings.CELERY_TASK_ALWAYS_EAGER and getattr(result, "failed", lambda: False)():
        return Response(
            {"detail": str(result.result) or "AI task failed. Check the server configuration."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return Response({"task_id": result.id}, status=status.HTTP_202_ACCEPTED)


class AIActionRateThrottle(ScopedRateThrottle):
    """Apply the configured AI scope only to AI-producing viewset actions."""

    scope_attr = 'ai_throttle_scope'


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

    @property
    def ai_throttle_scope(self):
        return 'ai' if getattr(self, 'action', None) in {
            'suggest_reply', 'classify', 'summarize'
        } else None

    def perform_create(self, serializer):
        ticket = serializer.save()
        enrich_ticket(ticket, ticket.description or '')

    @action(
        detail=True,
        methods=["post"],
        url_path="suggest-reply",
        throttle_classes=[AIActionRateThrottle],
    )
    def suggest_reply(self, request, pk=None):
        ticket = self.get_object()
        return _enqueue_ai_task(generate_ai_suggestion, ticket.pk)

    @action(
        detail=True,
        methods=["post"],
        url_path="classify",
        throttle_classes=[AIActionRateThrottle],
    )
    def classify(self, request, pk=None):
        ticket = self.get_object()
        return _enqueue_ai_task(classify_ticket, ticket.pk)

    @action(
        detail=True,
        methods=["post"],
        url_path="summarize",
        throttle_classes=[AIActionRateThrottle],
    )
    def summarize(self, request, pk=None):
        ticket = self.get_object()
        return _enqueue_ai_task(summarize_ticket, ticket.pk)

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


class AnalyticsPermission(permissions.BasePermission):
    """Permission for Analytics endpoints.
    * Unauthenticated -> 401.
    * Agents and Admins can view analytics.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            raise NotAuthenticated("Authentication credentials were not provided.")
        role = getattr(request.user, "role", "")
        return role in ("ADMIN", "AGENT") or request.user.is_staff


class AnalyticsOverviewView(APIView):
    """Provides key operational and AI metrics for the analytics dashboard."""

    permission_classes = [AnalyticsPermission]
    authentication_classes = [SessionAuthenticationWith401]

    def get(self, request):
        now = timezone.now()
        try:
            days = int(request.query_params.get("days", 14))
            days = max(1, min(days, 90))
        except (ValueError, TypeError):
            days = 14

        # 1. Total & Status Counts
        total_tickets = Ticket.objects.count()
        open_tickets = Ticket.objects.filter(status="open").count()
        resolved_tickets = Ticket.objects.filter(status="resolved").count()
        closed_tickets = Ticket.objects.filter(status="closed").count()

        # 2. Number of tickets per day
        start_date = (now - timedelta(days=days - 1)).date()
        daily_counts = {}
        for d in range(days):
            day_str = (start_date + timedelta(days=d)).isoformat()
            daily_counts[day_str] = 0

        window_start = timezone.make_aware(
            timezone.datetime.combine(start_date, timezone.datetime.min.time())
        )
        recent_tickets = Ticket.objects.filter(created_at__gte=window_start).values_list("created_at", flat=True)
        for created_dt in recent_tickets:
            day_key = created_dt.date().isoformat()
            if day_key in daily_counts:
                daily_counts[day_key] += 1

        tickets_per_day = [{"date": k, "count": v} for k, v in daily_counts.items()]

        # 3. Average first-reply time
        reply_times = []
        tickets_with_messages = Ticket.objects.all().prefetch_related("messages")
        for ticket in tickets_with_messages:
            first_reply = (
                ticket.messages.filter(message_type="agent", is_draft=False)
                .order_by("created_at")
                .first()
            )
            if first_reply and first_reply.created_at >= ticket.created_at:
                diff = (first_reply.created_at - ticket.created_at).total_seconds()
                reply_times.append(diff)

        avg_reply_seconds = round(sum(reply_times) / len(reply_times), 1) if reply_times else 0.0
        avg_reply_minutes = round(avg_reply_seconds / 60.0, 1)

        def format_duration(seconds: float) -> str:
            if seconds <= 0:
                return "N/A"
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            if hours > 0:
                return f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"
            return f"{max(1, minutes)}m"

        # 4. Percentage of AI suggestions that were accepted
        succeeded_suggestions = AILog.objects.filter(operation="suggest_reply", status="succeeded")
        total_suggestions = succeeded_suggestions.count()
        accepted_suggestions = TicketMessage.objects.filter(
            ai_log__operation="suggest_reply",
            is_ai_generated=False,
            is_draft=False,
        ).count()
        acceptance_rate = (
            round((accepted_suggestions / total_suggestions) * 100.0, 1)
            if total_suggestions > 0
            else 0.0
        )
        pending_suggestions = TicketMessage.objects.filter(
            ai_log__operation="suggest_reply",
            is_draft=True,
        ).count()

        # 5. Category breakdown
        category_counts = [
            {"category": "general", "label": "General Question", "count": Ticket.objects.filter(category="general").count()},
            {"category": "technical", "label": "Technical Question", "count": Ticket.objects.filter(category="technical").count()},
            {"category": "refund", "label": "Refund Request", "count": Ticket.objects.filter(category="refund").count()},
        ]

        # 6. Priority breakdown
        priority_counts = [
            {"priority": "high", "count": Ticket.objects.filter(priority="high").count()},
            {"priority": "medium", "count": Ticket.objects.filter(priority="medium").count()},
            {"priority": "low", "count": Ticket.objects.filter(priority="low").count()},
        ]

        return Response({
            "total_tickets": total_tickets,
            "open_tickets": open_tickets,
            "resolved_tickets": resolved_tickets,
            "closed_tickets": closed_tickets,
            "average_first_reply_time_seconds": avg_reply_seconds,
            "average_first_reply_time_minutes": avg_reply_minutes,
            "average_first_reply_time_formatted": format_duration(avg_reply_seconds),
            "ai_suggestions": {
                "total": total_suggestions,
                "accepted": accepted_suggestions,
                "pending": pending_suggestions,
                "acceptance_rate": acceptance_rate,
            },
            "tickets_per_day": tickets_per_day,
            "categories": category_counts,
            "priorities": priority_counts,
        })
