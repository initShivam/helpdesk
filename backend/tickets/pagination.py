from django.db.models import Count, Q
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .models import Ticket


class TicketPagination(PageNumberPagination):
    page_size = 30

    def get_paginated_response(self, data):
        stats = Ticket.objects.aggregate(
            total=Count("id"),
            open=Count("id", filter=Q(status="open")),
            high_urgent=Count("id", filter=Q(priority__in=("high", "urgent"))),
            resolved=Count("id", filter=Q(status__in=("resolved", "closed"))),
        )
        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
                "stats": stats,
            }
        )
