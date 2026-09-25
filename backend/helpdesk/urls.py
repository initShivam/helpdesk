"""URLs configuration for the helpdesk Django project."""
from django.contrib import admin
from django.urls import include, path

from .health import health

urlpatterns = [
    path("health/", health, name="health"),
    path('api/', include('tickets.urls')),
    path('api/auth/', include('accounts.urls')),
    path('api/agents/', include('accounts.agent_urls')),
    path('admin/', admin.site.urls),]
