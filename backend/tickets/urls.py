from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers
from .views import TicketViewSet, TicketMessageViewSet

# Primary router for tickets
router = DefaultRouter()
router.register(r'tickets', TicketViewSet, basename='ticket')

# Nested router for ticket messages
tickets_router = routers.NestedDefaultRouter(router, r'tickets', lookup='ticket')
tickets_router.register(r'messages', TicketMessageViewSet, basename='ticket-message')

urlpatterns = router.urls + tickets_router.urls
