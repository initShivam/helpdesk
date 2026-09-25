from django.urls import path
from .views import AgentViewSet
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'', AgentViewSet, basename='agent')

urlpatterns = router.urls
