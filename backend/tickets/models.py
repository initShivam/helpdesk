from django.db import models
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator

class Ticket(models.Model):
    STATUS_CHOICES = [
        ("open", "Open"),
        ("resolved", "Resolved"),
        ("closed", "Closed"),
    ]
    CATEGORY_CHOICES = [
        ("general", "General Question"),
        ("technical", "Technical Question"),
        ("refund", "Refund Request"),
    ]
    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
    ]

    ticket_number = models.CharField(max_length=20, unique=True)
    subject = models.CharField(max_length=255)
    requester_email = models.EmailField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="open")
    category = models.CharField(max_length=12, choices=CATEGORY_CHOICES, default="general")
    priority = models.CharField(max_length=6, choices=PRIORITY_CHOICES, default="medium")
    # AI-generated summary of the ticket (optional)
    ai_summary = models.TextField(null=True, blank=True)
    # Confidence score for AI-assigned category (0.0 - 1.0)
    ai_category_confidence = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )
    # Source of the ticket (e.g., 'web', 'email', 'api')
    source = models.CharField(max_length=20, default='web')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_tickets")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_tickets")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.ticket_number} - {self.subject}"

class TicketMessage(models.Model):
    MESSAGE_TYPE_CHOICES = [
        ("customer", "Customer"),
        ("agent", "Agent"),
        ("system", "System"),
    ]
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="sent_messages")
    body = models.TextField()
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPE_CHOICES, default="customer")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Message {self.id} on {self.ticket.ticket_number}"
