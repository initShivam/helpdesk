from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers
from .views import TicketViewSet, TicketMessageViewSet, AnalyticsOverviewView

# Primary router for tickets
router = DefaultRouter()
router.register(r'tickets', TicketViewSet, basename='ticket')

# Nested router for ticket messages
tickets_router = routers.NestedDefaultRouter(router, r'tickets', lookup='ticket')
tickets_router.register(r'messages', TicketMessageViewSet, basename='ticket-message')

urlpatterns = [
    path('analytics/overview', AnalyticsOverviewView.as_view(), name='analytics-overview-no-slash'),
    path('analytics/overview/', AnalyticsOverviewView.as_view(), name='analytics-overview'),
] + router.urls + tickets_router.urls
