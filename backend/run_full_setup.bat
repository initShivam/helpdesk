@echo off
rem Set PostgreSQL environment variables without trailing spaces
set "POSTGRES_DB=helpdesk"
set "POSTGRES_USER=postgres"
set "POSTGRES_PASSWORD=admin"
set "POSTGRES_HOST=localhost"
set "POSTGRES_PORT=5432"

rem Activate virtual environment
call .\.venv\Scripts\activate.bat

rem Verify connection and list tables (development data)
python test_connection.py

rem Reset the PostgreSQL development database (dev data will be lost)
python reset_db.py

rem Apply all migrations
python manage.py migrate --noinput

rem Run Django system check
python manage.py check

rem Start development server for verification (runs in background)
start "DjangoServer" cmd /C "python manage.py runserver 0.0.0.0:8000"

rem Wait a few seconds to allow server to start
timeout /T 5 >nul

exit /b 0
