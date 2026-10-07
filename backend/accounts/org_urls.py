from rest_framework.routers import DefaultRouter

from .views import DepartmentViewSet, TeamViewSet


router = DefaultRouter()
router.register("departments", DepartmentViewSet, basename="department")
router.register("teams", TeamViewSet, basename="team")

urlpatterns = router.urls
