from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tickets", "0009_whatsapp_error_detail")]

    operations = [
        migrations.RemoveField(
            model_name="whatsappnotification",
            name="twilio_message_sid",
        ),
        migrations.AddField(
            model_name="whatsappnotification",
            name="meta_message_id",
            field=models.CharField(blank=True, db_index=True, max_length=128),
        ),
    ]
