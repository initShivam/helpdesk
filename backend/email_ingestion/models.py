from django.db import models

from tickets.models import Ticket, TicketMessage


class InboundEmail(models.Model):
    message_id = models.CharField(max_length=998, unique=True)
    thread_id = models.CharField(max_length=998, blank=True, default="")
    sender_email = models.EmailField()
    subject = models.CharField(max_length=998, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name="inbound_emails",
    )
    ticket_message = models.OneToOneField(
        TicketMessage,
        on_delete=models.CASCADE,
        related_name="inbound_email",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class EmailAttachment(models.Model):
    inbound_email = models.ForeignKey(
        InboundEmail,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=255, blank=True)
    file = models.FileField(upload_to="email_attachments/%Y/%m/%d/")
    size_bytes = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
