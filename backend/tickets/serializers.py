from rest_framework import serializers
from .models import Ticket, TicketMessage
from email_ingestion.serializers import EmailAttachmentSerializer

class TicketSerializer(serializers.ModelSerializer):
    attachments = serializers.SerializerMethodField()
    resolution_note = serializers.CharField(required=False, allow_blank=True, max_length=10000, write_only=True)

    def get_attachments(self, obj):
        attachments = EmailAttachmentSerializer(
            [attachment for inbound in obj.inbound_emails.all() for attachment in inbound.attachments.all()],
            many=True,
            context=self.context,
        )
        return attachments.data

    """Serializer for the Ticket model.

    * `created_by`, `created_at`, and `updated_at` are read‑only – they are set automatically.
    * On create we automatically set `created_by` to the request user.
    * All model fields are exposed (including AI‑related ones) for future use.
    """

    classification = serializers.CharField(source="category", required=False)

    class Meta:
        model = Ticket
        fields = [
            "id",
            "ticket_number",
            "subject",
            "description",
            "requester_email",
            "status",
            "category",
            "classification",
            "priority",
            "ai_summary",
            "ai_category_confidence",
            "source",
            "created_by",
            "assigned_to",
            "created_at",
            "updated_at",
            "attachments",
            "resolution_note",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def create(self, validated_data):
        validated_data.pop("resolution_note", None)
        request = self.context.get("request")
        if request and hasattr(request, "user") and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("resolution_note", None)
        return super().update(instance, validated_data)


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
            "is_ai_generated",
            "is_draft",
        ]
        read_only_fields = [
            "id",
            "ticket",
            "sender",
            "created_at",
            "updated_at",
            "is_ai_generated",
        ]

    def create(self, validated_data):
        request = self.context.get("request")
        if request and hasattr(request, "user") and request.user.is_authenticated:
            validated_data["sender"] = request.user
        return super().create(validated_data)
