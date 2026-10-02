from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tickets", "0008_whatsapp_notifications")]

    operations = [
        migrations.AddField(
            model_name="whatsappnotification",
            name="error_detail",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
