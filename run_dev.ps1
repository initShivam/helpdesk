# Run development servers for Helpdesk project
# This PowerShell script starts the Django backend and the React/Vite frontend.
# It launches each process in a new window so you can see logs for both.

# Use the repository virtual environment so all backend dependencies are available.
$python = Join-Path $PSScriptRoot "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Backend virtual environment not found at $python. Create backend\.venv and install backend\requirements.txt first."
}

# Apply migrations before starting Django so a fresh checkout can log in.
& $python (Join-Path $PSScriptRoot "backend\manage.py") migrate --noinput
if ($LASTEXITCODE -ne 0) {
    throw "Django migrations failed with exit code $LASTEXITCODE."
}

# Start Django backend
Start-Process -FilePath $python -ArgumentList @("backend\manage.py", "runserver", "0.0.0.0:8000") -WorkingDirectory $PSScriptRoot -WindowStyle Normal -RedirectStandardOutput (Join-Path $PSScriptRoot "backend.log") -RedirectStandardError (Join-Path $PSScriptRoot "backend_err.log")

# Start React frontend (Vite)
Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "cd /d `"$PSScriptRoot\frontend`" && npm run dev -- --host 0.0.0.0" -WorkingDirectory $PSScriptRoot -WindowStyle Normal -RedirectStandardOutput (Join-Path $PSScriptRoot "frontend.log") -RedirectStandardError (Join-Path $PSScriptRoot "frontend_err.log")

# Poll the configured Gmail mailbox even when Celery/Redis are not running.
Start-Process -FilePath $python -ArgumentList @("backend\manage.py", "poll_emails") -WorkingDirectory $PSScriptRoot -WindowStyle Normal -RedirectStandardOutput (Join-Path $PSScriptRoot "email-poller.log") -RedirectStandardError (Join-Path $PSScriptRoot "email-poller_err.log")

Write-Host "Development services started. Backend: backend.log, Frontend: frontend.log, Gmail poller: email-poller.log"
