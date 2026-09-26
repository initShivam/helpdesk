# Running Helpdesk

## Prerequisites

- Docker Desktop with Compose support for the containerized setup.
- Python 3.12 or newer and `pip` for local backend work.
- Node.js 20 or newer and npm for the frontend.
- Git.

## Environment configuration

Copy `.env.example` to `.env` at the repository root and set the database,
session, email, and AI values required for the workflow you want to run.

Do not commit `.env` or real credentials. Gmail ingestion should use an
application password or the configured OAuth flow rather than a normal mailbox
password.

## Docker Compose

Start the full local stack from the repository root:

```bash
docker compose up --build
```

Services:

- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8000/api/`
- Health endpoint: `http://localhost:8000/health/`

Stop the stack with:

```bash
docker compose down
```

## Local backend

Create and activate a virtual environment, then install dependencies:

```powershell
python -m venv backend\.venv
backend\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

Apply migrations and start Django:

```powershell
python backend\manage.py migrate
python backend\manage.py runserver
```

The API is available at `http://127.0.0.1:8000/api/`.

## Local frontend

Install dependencies and start Vite:

```powershell
Set-Location frontend
npm ci
npm run dev
```

The frontend is available at `http://localhost:5173`.

## Email ingestion

Set these values in the root `.env`:

```text
EMAIL_IMAP_HOST=imap.gmail.com
EMAIL_IMAP_PORT=993
EMAIL_IMAP_USERNAME=your-support-mailbox@example.com
EMAIL_IMAP_PASSWORD=your-gmail-app-password
EMAIL_IMAP_MAILBOX=INBOX
EMAIL_IMAP_TIMEOUT=30
```

Run the worker and scheduler in separate terminals:

```powershell
celery -A helpdesk worker -l INFO --workdir backend
celery -A helpdesk beat -l INFO --workdir backend
```

The scheduled task polls every five minutes. It creates tickets and messages,
deduplicates `Message-ID` values, reuses tickets for matching thread
references, and stores attachments under `backend/media/`.

For a direct one-time poll without Celery or Redis:

```powershell
python backend\manage.py poll_emails --once
```

## Validation commands

Backend checks and tests:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test
```

Frontend type check and build:

```powershell
Set-Location frontend
.\node_modules\.bin\tsc --noEmit
npm run build
```

Playwright browser tests:

```powershell
Set-Location frontend
npx playwright install chromium
npm run e2e
```

Playwright starts the frontend on port `5174` and Django on port `8001`, using
the isolated PostgreSQL database configured by `E2E_POSTGRES_*`.
