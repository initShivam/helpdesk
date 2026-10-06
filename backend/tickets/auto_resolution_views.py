import math
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    AutoResolutionSettings,
    AutoResolutionAudit,
    Ticket,
    get_auto_resolution_settings,
)


def _require_admin(user):
    if getattr(user, "role", "") != "ADMIN" and not user.is_staff:
        raise PermissionDenied("Only administrators can manage AI auto-resolution.")


class AutoResolutionSettingsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        _require_admin(request.user)
        config = get_auto_resolution_settings()
        today = timezone.localdate()
        week_start = today - timedelta(days=today.weekday())
        audits = AutoResolutionAudit.objects.all()
        stats = audits.aggregate(
            auto_resolved_today=Count(
                "id",
                filter=Q(
                    decision="auto_sent",
                    send_status="sent",
                    updated_at__date=today,
                ),
            ),
            auto_resolved_this_week=Count(
                "id",
                filter=Q(
                    decision="auto_sent",
                    send_status="sent",
                    updated_at__date__gte=week_start,
                ),
            ),
            sent_successfully=Count("id", filter=Q(send_status="sent")),
            sent_failed=Count("id", filter=Q(send_status="failed")),
            sent_to_agent_review=Count("id", filter=Q(decision="agent_review")),
        )
        return Response({
            "enabled": config.enabled,
            "email_auto_reply": config.email_auto_reply,
            "whatsapp_auto_reply": config.whatsapp_auto_reply,
            "simulation_mode": config.simulation_mode,
            "minimum_threshold": config.minimum_threshold,
            "changed_at": config.changed_at,
            "changed_by": config.changed_by.username if config.changed_by else None,
            "stats": stats,
        })

    def patch(self, request):
        _require_admin(request.user)
        allowed = {
            "enabled",
            "email_auto_reply",
            "whatsapp_auto_reply",
            "simulation_mode",
            "minimum_threshold",
        }
        unknown = set(request.data) - allowed
        if unknown:
            raise ValidationError({"detail": "Unknown setting fields."})

        updates = {}
        for field in allowed - {"minimum_threshold"}:
            if field in request.data:
                value = request.data[field]
                if not isinstance(value, bool):
                    raise ValidationError({field: "Must be a boolean."})
                updates[field] = value
        if "minimum_threshold" in request.data:
            threshold = request.data["minimum_threshold"]
            if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
                raise ValidationError({
                    "minimum_threshold": "Must be a number between 0 and 1."
                })
            try:
                threshold = float(threshold)
            except OverflowError as exc:
                raise ValidationError({
                    "minimum_threshold": "Must be a number between 0 and 1."
                }) from exc
            if not math.isfinite(threshold) or not 0 <= threshold <= 1:
                raise ValidationError({
                    "minimum_threshold": "Must be a number between 0 and 1."
                })
            updates["minimum_threshold"] = threshold
        if not updates:
            raise ValidationError({"detail": "Provide at least one setting to update."})

        with transaction.atomic():
            get_auto_resolution_settings()
            config = AutoResolutionSettings.objects.select_for_update().get(pk=1)
            for field, value in updates.items():
                setattr(config, field, value)
            config.changed_by = request.user
            config.save()
        return self.get(request)


class AutoResolutionAuditView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, ticket_id):
        user = request.user
        if getattr(user, "role", "") not in {"ADMIN", "AGENT"} and not user.is_staff:
            raise PermissionDenied("You do not have permission to view auto-resolution details.")

        ticket = get_object_or_404(Ticket, pk=ticket_id)
        audit = AutoResolutionAudit.objects.filter(ticket=ticket).first()
        if audit is None:
            return Response({"decision": "not_started", "send_status": "not_sent"})

        return Response({
            "decision": audit.decision,
            "decision_reason": audit.decision_reason,
            "matched_ticket_ids": audit.matched_ticket_ids,
            "matched_similarities": audit.matched_similarities,
            "selected_match_id": audit.selected_match_id,
            "similarity_score": audit.similarity_score,
            "ai_confidence": audit.ai_confidence,
            "generated_response": audit.generated_response,
            "channel": audit.channel,
            "send_status": audit.send_status,
            "send_error": audit.send_error,
            "provider_result": audit.provider_result,
            "provider_message_id": audit.provider_message_id,
            "send_attempts": audit.send_attempts,
            "created_at": audit.created_at,
            "updated_at": audit.updated_at,
        })
