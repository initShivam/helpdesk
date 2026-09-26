# Helpdesk System – Architecture Overview

## Revised Phase Structure & Dependencies

| Phase | Description | Depends On |
|------|-------------|-------------|
| **Phase 0 – Foundation** | Project scaffolding, CI/CD, core services, shared utilities (logging, config, health checks). | – |
| **Phase 1 – Authentication & RBAC** | User & agent accounts, role definitions (ADMIN, AGENT), Django session authentication, permission checks in all backend endpoints. | Phase 0 |
| **Phase 2 – Ticket Management** | CRUD for tickets, ticket lifecycle, basic UI. | Phase 1 |
| **Phase 3 – AI Classification & Summary** | Text classification, automatic ticket summarisation, confidence scoring. | Phase 2 |
| **Phase 4 – Knowledge‑Base & RAG** | Retrieval‑augmented generation against KB, vector store abstraction (configurable embedding model). | Phase 3 |
| **Phase 5 – AI Suggested Replies** | Generate response drafts, store in `AISuggestion` model, human‑in‑the‑loop workflow. | Phase 4 |
| **Phase 6 – Email Ingestion** | Inbound email parsing, ticket creation from email, attachment handling. | Phase 2 (ticket schema) & Phase 5 |
| **Phase 7 – Dashboard & Analytics** | Ticket list, stats, AI performance metrics (accuracy, precision, recall, F1, confusion matrix), Prometheus/Grafana optional. | Phases 2‑6 |
| **Phase 8 – Production Hardening** | Helm charts, advanced tracing, security hardening, autoscaling, optional enterprise infra. | All previous phases |

### Dependency Flow (simplified)
```
Foundation → Auth/RBAC → Ticket Management → AI Classification → KB/RAG → AI Replies → Email Ingestion → Dashboard/Analytics → Production Hardening
```

---

## Database Model List (high‑level)

| Model | Key Fields | Relations |
|-------|------------|-----------|
| **User** | `id`, `email`, `name`, `hashed_password`, `created_at` | 1‑N **UserRole** |
| **Role** | `id`, `name` (ADMIN, AGENT) | Referenced by **UserRole** |
| **UserRole** | `user_id`, `role_id` | Joins **User** ↔ **Role** |
| **Ticket** | `id`, `ticket_number`, `subject`, `requester_email`, `status`, `category`, `priority`, `created_by` (FK User), `assigned_to` (FK User), `ai_summary`, `ai_category_confidence`, `source`, `created_at`, `updated_at` | 1‑N **TicketMessage**, 1‑N **Attachment**, 1‑N **AISuggestion** |
| **TicketMessage** | `id`, `ticket_id`, `author_id` (FK User), `content`, `created_at`, `updated_at` | N‑1 **Ticket**, optional N‑1 **Attachment** |
| **Attachment** | `id`, `ticket_message_id`, `filename`, `mime_type`, `size_bytes`, `storage_path`, `created_at` | N‑1 **TicketMessage** |
| **AISuggestion** | `id`, `ticket_id`, `content`, `model`, `confidence`, `status` (PENDING/ACCEPTED/REJECTED), `created_at`, `accepted_by` (FK User), `accepted_at` | N‑1 **Ticket** |
| **EmbeddingModelConfig** *(optional)* | `id`, `provider`, `model_name`, `is_active` | Used by RAG layer to select embedding model at runtime |
| **EvaluationMetric** *(optional)* | `id`, `ticket_id`, `metric_name`, `value`, `run_at` | N‑1 **Ticket** (stores accuracy/precision/etc. for later analysis) |

---

## Implementation Order (high‑level roadmap)
1. **Phase 0 – Foundation** – repo, CI/CD, logging, health checks.
2. **Phase 1 – Authentication & RBAC** – user/role models, Django sessions, admin UI.
3. **Phase 2 – Ticket Management** – ticket model, CRUD, UI.
4. **Phase 3 – AI Classification & Summary** – AI pipeline, confidence fields.
5. **Phase 4 – Knowledge‑Base & RAG** – vector store abstraction, configurable embedding model.
6. **Phase 5 – AI Suggested Replies** – `AISuggestion` model, suggestion workflow.
7. **Phase 6 – Email Ingestion** – email parser, attachment handling.
8. **Phase 7 – Dashboard & Analytics** – ticket view, AI metrics, optional Prometheus/Grafana.
9. **Phase 8 – Production Hardening** – Helm charts, tracing, security, optional enterprise infra.

## Authentication and Agent Administration

Users sign in with their username or email using Django session authentication.
Administrators can manage agent accounts from `/admin/agents` in the frontend.
The page supports creating and deleting agents; the `/api/agents/` API is
restricted to administrators and cannot create, modify, or delete admin accounts.

API rate limiting is enabled only when `DJANGO_ENV=production`. Production
limits are 100 requests/hour for anonymous clients, 1,000 requests/hour for
authenticated users, and 10 login attempts/hour. Throttle counters use Redis;
set `DJANGO_CACHE_URL` to the shared production Redis URL (it defaults to
`CELERY_BROKER_URL`).

## Playwright End-to-End Setup

Install the browser test tooling and its Chromium browser from `frontend/`:

```bash
npm install
npx playwright install chromium
```

Run the configured Playwright command when end-to-end tests are added:

```bash
npm run e2e
```

Playwright starts the frontend at `http://127.0.0.1:5174` and a dedicated Django
server at `http://127.0.0.1:8001`. The server uses a separate PostgreSQL 18 database
`helpdesk_e2e` (configured via `E2E_POSTGRES_*` environment variables in `.env`),
runs Django migrations before startup, and does not read the development PostgreSQL
database configuration. E2E database details are set in `.env`:
- `E2E_POSTGRES_DB=helpdesk_e2e` (database name)
- `E2E_POSTGRES_HOST=localhost` (PostgreSQL host)
- `E2E_POSTGRES_PORT=5433` (PostgreSQL port)
- `E2E_POSTGRES_USER=postgres` (PostgreSQL user)
- `E2E_POSTGRES_PASSWORD=admin` (PostgreSQL password)

The `playwright.config.ts` loads these variables automatically. The database is
isolated from development, and Playwright's configured server runs migrations
before startup. All generated Playwright artifacts are git-ignored.

To add tests for a requested behavior, use the repository's `/create-test` prompt.
It directs test authoring to the existing Django or Playwright conventions and
requires the Playwright E2E database to remain isolated on PostgreSQL.

---

*This document captures the architectural decisions and roadmap. Further code will be added in subsequent phases.*
