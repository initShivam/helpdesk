# Helpdesk Deployment Guide

This guide covers deploying the Helpdesk application using Docker Compose for a single-server setup, as well as an overview of deploying to Kubernetes via Helm.

## Prerequisites
- Docker Engine (v20.10+)
- Docker Compose (v2.0+)
- Minimum 2GB RAM

## Option 1: Docker Compose (Single Node)

### 1. Configuration
First, copy the example environment file and configure it:
```bash
cp .env.example .env
# Edit .env and supply your GEMINI_API_KEY, DJANGO_SECRET_KEY, and Gmail credentials.
```

### 2. Startup
Run the application in detached mode:
```bash
docker-compose up -d --build
```
This starts:
- **web**: Django application (port 8000)
- **frontend**: React application (port 5173 / port 80 based on target)
- **db**: PostgreSQL with pgvector (port 5432)
- **redis**: Message broker and cache (port 6379)
- **celery** & **celery-beat**: Background workers and cron scheduler
- **prometheus** & **grafana**: Metrics and observability (ports 9090, 3000)

### 3. Setup the Database
Run initial migrations:
```bash
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py createsuperuser
```

---

## Option 2: Kubernetes (Helm Chart)
If deploying for high availability, use the provided Helm chart.

### 1. Configure Values
Create a `values-production.yaml` overriding defaults:
```yaml
env:
  DJANGO_ENV: "production"
  # Use Kubernetes Secrets for these in a real setup
  GEMINI_API_KEY: "..."
  DJANGO_SECRET_KEY: "..."
```

### 2. Install Release
```bash
helm upgrade --install helpdesk ./helm/helpdesk -f values-production.yaml --namespace helpdesk --create-namespace
```

---

## Operations & Observability

### Monitoring
- **Prometheus**: Accessible at `http://localhost:9090`. Scrapes Django at `/metrics` and Celery via `celery-exporter`.
- **Grafana**: Accessible at `http://localhost:3000`. Login with `admin / admin`. Import a Django dashboard template (e.g., ID 17658).

### Backups & Restore
PostgreSQL and the pgvector extension data are backed up using standard tools. See `scripts/backup.sh` and `scripts/restore.sh`.
```bash
# Take a backup
./scripts/backup.sh
# Restore a backup
./scripts/restore.sh
```
