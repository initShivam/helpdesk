from rest_framework import serializers

from .models import EmailAttachment


class EmailAttachmentSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = EmailAttachment
        fields = ["id", "filename", "content_type", "size_bytes", "download_url"]

    def get_download_url(self, obj):
        request = self.context.get("request")
        path = f"/api/tickets/{obj.inbound_email.ticket_id}/attachments/{obj.pk}/"
        return request.build_absolute_uri(path) if request else path
