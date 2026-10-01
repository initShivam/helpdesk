from django.urls import path

from .views import SyncMailboxView

urlpatterns = [
    path("sync/", SyncMailboxView.as_view(), name="email-sync"),
]
