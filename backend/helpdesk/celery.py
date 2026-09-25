import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "helpdesk.settings")

app = Celery("helpdesk")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks(["email_ingestion"])
