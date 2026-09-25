from rest_framework import serializers
from .models import Ticket, TicketMessage

class TicketSerializer(serializers.ModelSerializer):
    """Serializer for the Ticket model.

    * `created_by`, `created_at`, and `updated_at` are read‑only – they are set automatically.
    * On create we automatically set `created_by` to the request user.
    * All model fields are exposed (including AI‑related ones) for future use.
    """

    class Meta:
        model = Ticket
        fields = [
            "id",
            "ticket_number",
            "subject",
            "requester_email",
            "status",
            "category",
            "priority",
            "ai_summary",
            "ai_category_confidence",
            "source",
            "created_by",
            "assigned_to",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def create(self, validated_data):
        request = self.context.get("request")
        if request and hasattr(request, "user") and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        return super().create(validated_data)


class TicketMessageSerializer(serializers.ModelSerializer):
    body = serializers.CharField(required=True, allow_blank=False)
    """Serializer for TicketMessage.

    `ticket` and `sender` are read‑only; `sender` is set to the authenticated user on create.
    """

    class Meta:
        model = TicketMessage
        fields = [
            "id",
            "ticket",
            "sender",
            "body",
            "message_type",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "ticket", "sender", "created_at", "updated_at"]

    def create(self, validated_data):
        request = self.context.get("request")
        if request and hasattr(request, "user") and request.user.is_authenticated:
            validated_data["sender"] = request.user
        return super().create(validated_data)
