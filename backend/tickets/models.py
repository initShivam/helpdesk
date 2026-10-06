from django.db import models
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
import uuid

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


class ResolvedTicketKnowledge(models.Model):
    """Cached embedding for a human-resolved ticket and its agent response."""

    ticket = models.OneToOneField(
        Ticket,
        on_delete=models.CASCADE,
        related_name="resolution_knowledge",
    )
    problem_text = models.TextField()
    resolution_text = models.TextField()
    embedding = models.JSONField(default=list, blank=True)
    embedding_model = models.CharField(max_length=100, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class AutoResolutionSettings(models.Model):
    """Database-backed runtime controls for the auto-resolution worker."""

    enabled = models.BooleanField(default=False)
    email_auto_reply = models.BooleanField(default=True)
    whatsapp_auto_reply = models.BooleanField(default=False)
    simulation_mode = models.BooleanField(default=True)
    minimum_threshold = models.FloatField(
        default=0.85,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )
    changed_at = models.DateTimeField(auto_now=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="auto_resolution_setting_changes",
    )


def get_auto_resolution_settings():
    return AutoResolutionSettings.objects.get_or_create(pk=1)[0]


class AutoResolutionAudit(models.Model):
    DECISION_CHOICES = [
        ("processing", "Processing"),
        ("agent_review", "Agent review"),
        ("simulation", "Simulation"),
        ("auto_send", "Auto-send"),
        ("auto_sent", "Auto-sent"),
    ]
    SEND_STATUS_CHOICES = [
        ("not_sent", "Not sent"),
        ("pending", "Pending"),
        ("sending", "Sending"),
        ("sent", "Sent"),
        ("failed", "Failed"),
        ("unavailable", "Unavailable"),
    ]
    CHANNEL_CHOICES = [
        ("email", "Email"),
        ("whatsapp", "WhatsApp"),
        ("", "Unknown"),
    ]

    ticket = models.OneToOneField(
        Ticket,
        on_delete=models.CASCADE,
        related_name="auto_resolution_audit",
    )
    matched_ticket_ids = models.JSONField(default=list, blank=True)
    matched_similarities = models.JSONField(default=list, blank=True)
    selected_match_id = models.PositiveBigIntegerField(null=True, blank=True)
    similarity_score = models.FloatField(null=True, blank=True)
    ai_confidence = models.FloatField(null=True, blank=True)
    generated_response = models.TextField(blank=True)
    channel = models.CharField(max_length=16, choices=CHANNEL_CHOICES, blank=True)
    decision = models.CharField(max_length=16, choices=DECISION_CHOICES, default="processing")
    decision_reason = models.CharField(max_length=160, blank=True)
    send_status = models.CharField(max_length=16, choices=SEND_STATUS_CHOICES, default="not_sent")
    send_error = models.CharField(max_length=80, blank=True)
    provider_result = models.CharField(max_length=80, blank=True)
    provider_message_id = models.CharField(max_length=128, blank=True)
    send_attempts = models.PositiveSmallIntegerField(default=0)
    ai_log = models.ForeignKey(
        "tickets.AILog",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="auto_resolution_audits",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


class ResolutionNotification(models.Model):
    STATUS_CHOICES = [("pending", "Pending"), ("sending", "Sending"), ("sent", "Sent"), ("failed", "Failed")]
    MAX_ATTEMPTS = 3

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="resolution_notifications")
    recipient_email = models.EmailField()
    subject = models.CharField(max_length=255)
    issue_summary = models.TextField(blank=True)
    resolution_note = models.TextField(blank=True)
    notification_type = models.CharField(max_length=32, default="resolution")
    delivery_status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    attempt_count = models.PositiveSmallIntegerField(default=0)
    error_detail = models.CharField(max_length=160, blank=True)
    event_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class CustomerContact(models.Model):
    """Opt-in WhatsApp contact details keyed to the ticket requester email."""
    email = models.EmailField(unique=True)
    whatsapp_number = models.CharField(max_length=16, blank=True)
    whatsapp_consent = models.BooleanField(default=False)
    whatsapp_consent_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class WhatsAppNotification(models.Model):
    STATUS_CHOICES = [(value, value.title()) for value in
                      ("pending", "queued", "sent", "delivered", "read", "failed")]
    MAX_ATTEMPTS = 3
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="whatsapp_notifications")
    customer = models.ForeignKey(CustomerContact, on_delete=models.SET_NULL, null=True, related_name="whatsapp_notifications")
    recipient_number = models.CharField(max_length=16)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    meta_message_id = models.CharField(max_length=128, blank=True, db_index=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    error_code = models.CharField(max_length=40, blank=True)
    error_detail = models.CharField(max_length=255, blank=True)
    event_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        ordering = ["-created_at"]

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
