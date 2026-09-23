from django.contrib import admin
from .models import Ticket

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('ticket_number', 'subject', 'status', 'priority', 'created_at')
    search_fields = ('ticket_number', 'subject', 'requester_email')
    list_filter = ('status', 'category', 'priority')
