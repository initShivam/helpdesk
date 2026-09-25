import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'helpdesk.settings')
import django
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='testuser').exists():
    User.objects.create_user(username='testuser', password='testpass')
    print('Created testuser')
else:
    print('testuser already exists')
