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
        ("urgent", "Urgent"),
    ]

    ticket_number = models.CharField(max_length=20, unique=True)
    subject = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
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

    @property
    def classification(self) -> str:
        return self.category

    @classification.setter
    def classification(self, value: str) -> None:
        self.category = value

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
    is_ai_generated = models.BooleanField(default=False)
    is_draft = models.BooleanField(default=False)
    ai_log = models.ForeignKey(
        "tickets.AILog",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="messages",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Message {self.id} on {self.ticket.ticket_number}"


class AILog(models.Model):
    STATUS_CHOICES = [
        ("started", "Started"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
    ]

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="ai_logs")
    model = models.CharField(max_length=100)
    operation = models.CharField(max_length=50)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="started")
    sanitized_prompt = models.TextField(blank=True)
    response_text = models.TextField(blank=True)
    retrieved_document_ids = models.JSONField(default=list, blank=True)
    token_usage = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.operation} for {self.ticket.ticket_number} ({self.status})"
