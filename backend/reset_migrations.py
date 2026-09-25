import os
import django

# Ensure Django settings module is set
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'helpdesk.settings')

django.setup()

from django.db import connection

with connection.cursor() as cursor:
    # Delete migration records for admin and accounts apps
    cursor.execute("DELETE FROM django_migrations WHERE app IN ('admin','accounts');")
    # Optionally, drop tables for these apps (will be recreated by migrations)
    # Get table names from models
    # We'll just drop all tables to start fresh (dangerous but for dev)
    cursor.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    # Reset sequence counters
    cursor.execute("GRANT ALL ON SCHEMA public TO postgres; GRANT ALL ON SCHEMA public TO public;")

print('Migration history cleared and schema reset.')
