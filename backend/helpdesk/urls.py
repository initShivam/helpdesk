"""URLs configuration for the helpdesk Django project."""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('api/', include('tickets.urls')),
    path('api/auth/', include('accounts.urls')),
    path('api/agents/', include('accounts.agent_urls')),
    path('admin/', admin.site.urls),]
