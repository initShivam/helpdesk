from django.contrib import admin
from .models import AutoResolutionAudit, AutoResolutionSettings, ResolvedTicketKnowledge, Ticket

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('ticket_number', 'subject', 'status', 'priority', 'created_at')
    search_fields = ('ticket_number', 'subject', 'requester_email')
    list_filter = ('status', 'category', 'priority')


@admin.register(AutoResolutionAudit)
class AutoResolutionAuditAdmin(admin.ModelAdmin):
    list_display = ("ticket", "decision", "similarity_score", "ai_confidence", "send_status", "created_at")
    list_filter = ("decision", "send_status")
    search_fields = ("ticket__ticket_number", "ticket__subject")
    readonly_fields = (
        "ticket",
        "matched_ticket_ids",
        "matched_similarities",
        "selected_match_id",
        "similarity_score",
        "ai_confidence",
        "generated_response",
        "channel",
        "decision",
        "decision_reason",
        "send_status",
        "send_error",
        "provider_result",
        "provider_message_id",
        "send_attempts",
        "ai_log",
        "created_at",
        "updated_at",
    )


@admin.register(AutoResolutionSettings)
class AutoResolutionSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "enabled",
        "email_auto_reply",
        "whatsapp_auto_reply",
        "simulation_mode",
        "minimum_threshold",
        "changed_at",
    )
    readonly_fields = ("changed_at", "changed_by")

    def save_model(self, request, obj, form, change):
        obj.pk = 1
        obj.changed_by = request.user
        super().save_model(request, obj, form, change)

    def has_add_permission(self, request):
        return not AutoResolutionSettings.objects.filter(pk=1).exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ResolvedTicketKnowledge)
class ResolvedTicketKnowledgeAdmin(admin.ModelAdmin):
    list_display = ("ticket", "embedding_model", "updated_at")
    search_fields = ("ticket__ticket_number", "ticket__subject")
    readonly_fields = ("ticket", "problem_text", "resolution_text", "embedding", "embedding_model", "updated_at")
