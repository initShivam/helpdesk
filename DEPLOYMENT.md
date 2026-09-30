# Helpdesk deployment guide

This guide is provider-neutral. It documents single-host Docker Compose deployment and the operational decisions that must be made before a production launch. No Kubernetes chart is included yet.

## Requirements

- Docker Engine with the Compose v2 plugin
- At least 2 GB RAM for a small development or evaluation instance; size production for measured load
- A public HTTPS reverse proxy/load balancer in front of the Compose frontend
- A persistent, encrypted volume and an off-host backup destination for production data

## Configure production

1. Copy `.env.example` to `.env` on the host. Do not commit `.env` or put secrets in source control.
2. Set unique values for `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`, `GRAFANA_ADMIN_PASSWORD`, and any enabled AI or Gmail credentials. Use a secret manager or restricted deployment secret injection in production.
3. Set `DJANGO_ENV=production`, `DJANGO_DEBUG=False`, `DJANGO_ALLOWED_HOSTS` to the application hostnames, and `FRONTEND_URL=https://<frontend-host>`.
4. Set PostgreSQL credentials to match the values injected into the `db` service. Set a strong Grafana password even when the monitoring profile is disabled.
5. Decide backup retention, recovery point objective, recovery time objective, alert ownership, and Gmail OAuth/token handling before accepting production traffic.

The production Compose file requires `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, and `GRAFANA_ADMIN_PASSWORD`. Django additionally requires a production `DJANGO_SECRET_KEY` and explicit `DJANGO_ALLOWED_HOSTS`. `FRONTEND_URL` must use HTTPS. The frontend container listens on port 80 and is published only on host loopback by default; terminate TLS at a trusted reverse proxy and forward `/api/` and `/health/` to it. Do not expose PostgreSQL, Redis, Prometheus, or Grafana directly to the public Internet.

## Start and upgrade

```sh
docker compose -f docker-compose.production.yml config
docker compose -f docker-compose.production.yml up -d --build
docker compose -f docker-compose.production.yml exec web python manage.py migrate
docker compose -f docker-compose.production.yml exec web python manage.py createsuperuser
```

After changing application code or dependencies, rebuild and redeploy with `up -d --build`. Review migrations before applying them. Collectstatic runs when the web container starts. Django and Celery use the same application image and environment. Email polling is scheduled by Celery Beat; configure only one Beat instance.

The local development stack uses `docker-compose.yml` and intentionally enables the Vite development server. Start it with `docker compose up --build`; it is not a production deployment.

## Monitoring

Start the optional local monitoring stack with:

```sh
docker compose -f docker-compose.production.yml --profile monitoring up -d
```

Prometheus and Grafana bind to host loopback. Prometheus scrapes Django's `/metrics` endpoint and the Celery exporter. Grafana receives a provisioned Prometheus data source at startup. Add dashboards and alert routing appropriate to the selected operations team before launch; the current alert rules flag unreachable scrape targets only.

## Backup and restore drill

Run backups from the repository root while the selected Compose deployment is running:

```sh
COMPOSE_FILE=docker-compose.production.yml ./scripts/backup.sh
COMPOSE_FILE=docker-compose.production.yml ./scripts/restore.sh backups/helpdesk_<UTC timestamp>
```

The backup includes a PostgreSQL custom-format dump (including pgvector data) and the media volume contents, with SHA-256 checksums. Restore verifies checksums and archive readability, then restores into a newly named `helpdesk_restore_drill_*` database and an ignored local `restore-drill/` directory. It does not overwrite the live database. Inspect restored rows, attachments, and application behavior, record elapsed times, then remove the drill database and local files using an explicit operator-approved cleanup. Copy backups off host, encrypt them, restrict access, and test the actual production storage/retention path. A live restore drill has not been run in this repository environment.

## Kubernetes

There is currently no Helm chart in this repository. Kubernetes deployment needs a selected cloud/region, ingress and TLS design, managed or self-hosted PostgreSQL/Redis, secret-management strategy, storage class, scaling policy, monitoring/alert ownership, and backup/restore objectives. Implement and validate a chart after those inputs are agreed; do not run Helm commands against a nonexistent chart.

## Release checklist

- Select provider, region, production hostname, TLS/ingress, and secret manager.
- Set monitoring dashboards, alert delivery, backup retention, RPO/RTO, and Gmail credential/token policy.
- Complete a restore drill in the target environment and retain evidence.
- Run backend tests, frontend typecheck/build, E2E, production Django checks, and image builds in CI.
- Review the OWASP/security findings and dependency scan for the release commit.
- Obtain named stakeholder approval before tagging or releasing `v1.0.0-rc`.
