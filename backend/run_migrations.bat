@echo off
set POSTGRES_DB=helpdesk
set POSTGRES_USER=postgres
set POSTGRES_PASSWORD=admin
set POSTGRES_HOST=localhost
set POSTGRES_PORT=5432
call .\.venv\Scripts\activate.bat
python manage.py migrate --noinput
