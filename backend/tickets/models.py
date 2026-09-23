from django.db import models
from django.conf import settings

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
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_tickets")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_tickets")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.ticket_number} - {self.subject}"
