import os, psycopg2, sys
print('POSTGRES_HOST env:', os.getenv('POSTGRES_HOST'))
try:
    conn = psycopg2.connect(
        dbname=os.getenv('POSTGRES_DB', 'helpdesk'),
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', 'admin'),
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=os.getenv('POSTGRES_PORT', '5432'),
    )
    print('Connection successful')
    cur = conn.cursor()
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
    tables = cur.fetchall()
    print('Tables:', tables)
    conn.close()
except Exception as e:
    print('Error:', e)
