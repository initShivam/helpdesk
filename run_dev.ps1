# Run development servers for Helpdesk project
# This PowerShell script starts the Django backend and the React/Vite frontend.
# It launches each process in a new window so you can see logs for both.

# Start Django backend
Start-Process -FilePath "python" -ArgumentList "backend\manage.py", "runserver", "0.0.0.0:8000" -WorkingDirectory "$PSScriptRoot" -WindowStyle Normal -RedirectStandardOutput "backend.log" -RedirectStandardError "backend_err.log"

# Start React frontend (Vite)
Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "cd", ".\frontend && npm run dev" -WorkingDirectory "$PSScriptRoot" -WindowStyle Normal -RedirectStandardOutput "frontend.log" -RedirectStandardError "frontend_err.log"

Write-Host "Development servers started. Backend logs: backend.log, Frontend logs: frontend.log"
