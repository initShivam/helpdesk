import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'helpdesk.settings')
django.setup()
from rest_framework.test import APIClient
client = APIClient()
response = client.get('/api/tickets/')
print('status:', response.status_code)
print('data:', response.data)
print('headers:', dict(response.items()))
