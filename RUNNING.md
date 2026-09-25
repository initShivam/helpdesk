# Running the Helpdesk Application

## Prerequisites
- **Docker Desktop** (optional, for containerized run) with Docker Compose support.
- **Python 3.12+** and `pip` (for local backend execution).
- **Bun** (recommended for the frontend). Install via:
  ```
  curl -fsSL https://bun.sh/install | bash
  ```
- **Git** (for version control).

## Option 1: Run with Docker Compose (recommended for production‑like environment)
1. Ensure Docker Desktop is running.
2. From the project root, execute:
   ```
   docker compose up --build
   ```
3. The services will be available at:
   - Backend API: `http://localhost:8000/api/`
   - Frontend UI: `http://localhost:5173/`

## Option 2: Run locally without Docker
Before starting the backend locally, ensure the project-root `.env` contains the
PostgreSQL settings (`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`,
`POSTGRES_HOST`, and `POSTGRES_PORT`). Django loads this file automatically.

### Backend (Django)
```bash
# Create a virtual environment
python -m venv venv
# Activate it (PowerShell)
venv\Scripts\Activate.ps1
# Install dependencies
pip install -r backend/requirements.txt
# Apply migrations
python backend/manage.py migrate
# Start the development server
python backend/manage.py runserver
```
The API will be reachable at `http://127.0.0.1:8000/api/`.

### Email ingestion worker

Set the IMAP settings in the project-root `.env`:

```text
EMAIL_IMAP_HOST=imap.gmail.com
EMAIL_IMAP_PORT=993
EMAIL_IMAP_USERNAME=your-support-mailbox@example.com
EMAIL_IMAP_PASSWORD=your-gmail-app-password
EMAIL_IMAP_MAILBOX=INBOX
EMAIL_IMAP_TIMEOUT=30
```

Apply migrations, then run the worker and scheduler in separate terminals:

```bash
python backend/manage.py migrate
celery -A helpdesk worker -l INFO --workdir backend
celery -A helpdesk beat -l INFO --workdir backend
```

The scheduler runs `email_ingestion.tasks.fetch_emails` every five minutes.
Inbound emails are stored as tickets and ticket messages, duplicate
`Message-ID` values are ignored, replies with matching thread references reuse
the original ticket, and attachments are saved under `backend/media/`.

If Docker/Redis is unavailable, run the local polling command instead. It
connects directly to IMAP and does not require Celery or Redis:

```bash
python backend/manage.py poll_emails
```

For a one-time mailbox check:

```bash
python backend/manage.py poll_emails --once
```

### Frontend (React + Vite + Bun)
```bash
cd frontend
# Install dependencies using Bun
bun install
# Start the development server
bun dev
```
Open `http://localhost:5173` in your browser.

## Notes
- The frontend fetches tickets from `http://localhost:8000/api/tickets/`. Adjust the URL if the backend is hosted elsewhere.
- In production, set environment variables for `DJANGO_SECRET_KEY`, `POSTGRES_*`, etc., as described in the `backend/.env.example` file (if added later).
