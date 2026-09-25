import os
import psycopg2

# Ensure environment variables are set (fallback defaults)
user = os.getenv('POSTGRES_USER', 'postgres')
password = os.getenv('POSTGRES_PASSWORD', 'admin')
host = os.getenv('POSTGRES_HOST', 'localhost')
port = os.getenv('POSTGRES_PORT', '5432')

# Connect to default 'postgres' database to manage databases
conn = psycopg2.connect(dbname='postgres', user=user, password=password, host=host, port=port)
conn.autocommit = True
cur = conn.cursor()

cur.execute('DROP DATABASE IF EXISTS helpdesk;')
cur.execute('CREATE DATABASE helpdesk;')

print('PostgreSQL database "helpdesk" has been reset.')
