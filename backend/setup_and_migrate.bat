@echo off
rem Set PostgreSQL environment variables without trailing spaces
set "POSTGRES_DB=helpdesk"
set "POSTGRES_USER=postgres"
set "POSTGRES_PASSWORD=admin"
set "POSTGRES_HOST=localhost"
set "POSTGRES_PORT=5432"

rem Activate virtual environment
call .\.venv\Scripts\activate.bat

rem -------------------------------------------------------------------
rem 1. Verify connection and list existing tables (development data)
python test_connection.py

rem -------------------------------------------------------------------
rem 2. Reset the PostgreSQL development database (dev data will be lost)
python reset_db.py

rem -------------------------------------------------------------------
rem 3. Apply all migrations
python manage.py migrate --noinput

rem -------------------------------------------------------------------
rem 4. Run Django system check
python manage.py check

rem -------------------------------------------------------------------
rem 5. Start the development server (will run until stopped)
rem For verification we run it in background for a few seconds then stop.
start "DjangoServer" cmd /C "python manage.py runserver 0.0.0.0:8000"

rem Give the server a moment to start
ping -n 5 127.0.0.1 >nul

rem Optionally you could add a request here to verify HTTP response, but omitted.

exit /b 0
