import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tickets", "0007_resolutionnotification")]
    operations = [
        migrations.CreateModel(
            name="CustomerContact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(max_length=254, unique=True)),
                ("whatsapp_number", models.CharField(blank=True, max_length=16)),
                ("whatsapp_consent", models.BooleanField(default=False)),
                ("whatsapp_consent_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="WhatsAppNotification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("recipient_number", models.CharField(max_length=16)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("queued", "Queued"), ("sent", "Sent"), ("delivered", "Delivered"), ("read", "Read"), ("failed", "Failed")], default="pending", max_length=10)),
                ("twilio_message_sid", models.CharField(blank=True, db_index=True, max_length=64)),
                ("attempt_count", models.PositiveSmallIntegerField(default=0)),
                ("error_code", models.CharField(blank=True, max_length=40)),
                ("event_key", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_attempt_at", models.DateTimeField(blank=True, null=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("failed_at", models.DateTimeField(blank=True, null=True)),
                ("customer", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="whatsapp_notifications", to="tickets.customercontact")),
                ("ticket", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="whatsapp_notifications", to="tickets.ticket")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
