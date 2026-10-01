# Helpdesk deployment on Render

The Render Blueprint in [`render.yaml`](render.yaml) describes a Singapore deployment with a Django API, static React frontend, Celery worker and Beat service, Render Postgres, and Render Key Value. Render Postgres supports the `pgvector` extension used by this app; the migration enables it. The frontend is a static site on Render's global CDN, so it has no region setting. [Blueprint reference](https://render.com/docs/blueprint-spec), [Postgres extensions](https://render.com/docs/postgresql-extensions).

## Before syncing the Blueprint

The Blueprint creates resources; it does not attach to an existing Render deployment unless service/database names match. If you already have these services, compare their names/settings first and back up the database before syncing. Do not create a second production database by accident.

1. Push this repository to a Git provider connected to Render.
2. In Render, create a Blueprint from the repository and review every proposed service before confirming resource creation. The app, workers, Postgres, and Redis are configured for Singapore. Confirm compute/database plans in the dashboard.
3. For the prompted `DJANGO_ALLOWED_HOSTS`, provide the API service hostname, e.g. `helpdesk-api.onrender.com` (and any custom API hostname). For `FRONTEND_URL`, use the exact frontend origin, e.g. `https://helpdesk-frontend.onrender.com`. For `VITE_API_BASE_URL`, use the API's full HTTPS origin, e.g. `https://helpdesk-api.onrender.com`.
4. Supply the OpenAI API key for text generation, an Ollama service URL reachable from Render, Gmail IMAP username/app password, and an S3-compatible private bucket name, region, access key, and secret key. For AWS S3 leave `AWS_S3_ENDPOINT_URL` blank; for R2 or another S3-compatible service enter its endpoint URL. Create the bucket first and configure private access with server-side encryption and a narrowly scoped service credential.
5. Confirm the frontend and backend URLs are correct, then deploy. The API runs migrations before deploy and collects static files when starting.
6. Create the first administrator using the Render Shell for `helpdesk-api`: `python manage.py createsuperuser`.

Render prompts for `sync: false` Blueprint variables on initial creation only. To update those values later, edit the service's Environment page in the Render Dashboard. Custom domains must be added to both `DJANGO_ALLOWED_HOSTS` and `FRONTEND_URL`; set `VITE_API_BASE_URL` to the API domain and redeploy the static site.

## Service layout

- **helpdesk-api**: Django/Gunicorn web service, health check at `/health/`, Render Postgres via private connection string.
- **helpdesk-frontend**: Vite-built React static site; `VITE_API_BASE_URL` points to the API origin.
- **helpdesk-celery**: Celery background worker for AI tasks and email ingestion.
- **helpdesk-celery-beat**: single scheduler instance for polling Gmail every five minutes.
- **helpdesk-db**: managed PostgreSQL 16 with `pgvector` enabled by migration.
- **helpdesk-redis**: persistent Render Key Value for Celery broker/results. Keep it in the same region as the app and database.

Render Blueprints let the worker and API share the database, Redis, secret, and Gmail/AI values through service references; secret values are not stored in this repository. [Blueprint environment variables](https://render.com/docs/blueprint-spec#setting-environment-variables).

## Ollama embeddings

Install Ollama on a machine that can reach the API and worker services, then
download the model with `ollama pull nomic-embed-text`. Set
`OLLAMA_BASE_URL` on Render to that Ollama service's reachable HTTP URL. The
default `http://localhost:11434` is for a backend running on the same machine;
it does not refer to your workstation from a Render container. Keep the Ollama
endpoint private and allow access only from the application services.

After deploying the updated backend, run `python manage.py reindex_embeddings`
from the API service shell. The command updates old OpenAI vectors in place,
one document or chunk at a time; if Ollama becomes unavailable, rerun the same
command to continue. No database schema migration is required.

## Media storage

Email attachments use Django's default storage. Render services have separate ephemeral filesystems, so the Blueprint enables the new S3-compatible media backend for both the API and worker. Provide the same private bucket settings to both services; the API streams authorized attachments from storage. Render documents that local files are lost on deploy/restart. [Render filesystem behavior](https://render.com/docs/deploys).

## Monitoring and operations

The existing Prometheus/Grafana Compose profile is for local/self-hosted operation; it is not part of the Render Blueprint. Use Render service/database metrics and configure alert delivery in the Render workspace (or select an external monitoring service). Set and review the alert recipients before production traffic.

Render Postgres provides managed backup/restore features depending on the selected plan. Define retention and recovery objectives, then conduct and record a restore in a separate database before production launch. The repository's `scripts/backup.sh` and `scripts/restore.sh` are Docker Compose drills and do not operate on Render services. For an off-platform logical backup, use the external connection command shown on the Render Postgres Info page with `pg_dump`, store the dump encrypted off-site, and rehearse restore to a separate database. [Render Postgres backups](https://render.com/docs/postgresql-backups).

## Remaining release gates

- Create the private object-storage bucket and verify attachment upload/download from both API and worker.
- Select and set the Render plans that meet traffic, uptime, and recovery needs; free/low-resource plans may sleep or lack the persistence/backup behavior needed by production.
- Configure alert delivery, backup retention, RPO/RTO, and Gmail credential rotation.
- Run the production-like backup/restore drill and security review; record the evidence.
- Obtain a named stakeholder's sign-off before creating the `v1.0.0-rc` tag.
