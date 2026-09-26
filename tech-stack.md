# Technical Architecture

## Applications and services

| Component | Responsibility |
| --- | --- |
| Django | API, authentication, admin, migrations, health endpoint |
| Django REST Framework | JSON API, serializers, viewsets, permissions |
| React + TypeScript + Vite | Agent and administrator user interface |
| Tailwind CSS | Frontend styling |
| React Query | Server-state caching and request lifecycle |
| PostgreSQL | Application data, sessions, tickets, messages, and knowledge-base metadata |
| pgvector | Optional vector storage when the PostgreSQL extension is available |
| Redis | Celery broker/result backend and production cache |
| Celery worker | Email polling and AI suggestion jobs |
| Celery beat | Five-minute email polling schedule |
| Docker Compose | Local multi-service orchestration |
| GitHub Actions | Backend checks, frontend checks, and Docker image builds |

## Backend boundaries

- `accounts/` owns the custom `User` model, authentication, roles, and agent
  administration.
- `tickets/` owns tickets, messages, ticket permissions, AI draft workflows,
  and AI request logging.
- `email_ingestion/` owns IMAP access, email parsing, duplicate/thread
  detection, and attachment persistence.
- `knowledge_base/` owns document ingestion, chunking, embeddings, and
  similarity retrieval.
- `helpdesk/` owns project settings, URL routing, Celery configuration, and
  health checks.

## Authentication and security

Authentication uses Django sessions with CSRF protection. API access uses the
custom session authentication class. CORS and CSRF trusted origins are
configured for the local Vite ports. Production throttling and Redis-backed
caching are enabled when `DJANGO_ENV=production`.

Attachments are exposed through ticket-scoped authenticated endpoints. AI input
is sanitized before provider requests, and AI calls are recorded in the
`AILog` model without storing unsanitized prompts.

## AI and retrieval

Gemini provides generation and provider-backed embeddings when configured.
When Gemini or pgvector is unavailable locally, deterministic JSON embeddings
provide a development fallback. Docker Compose uses the pgvector PostgreSQL
image and enables the vector store.

The AI flow is:

1. Load ticket conversation content.
2. Sanitize prompt content.
3. Retrieve relevant knowledge-base chunks.
4. Send structured context to Gemini.
5. Store the generated reply as an AI draft.
6. Let an agent edit or accept the draft.

## Data and configuration

Runtime configuration is loaded from the project-root `.env`; `.env.example`
documents the supported variables. Database migrations are stored beside their
own Django app. Uploaded attachments are stored under the backend media
directory or the configured container volume.

## Testing boundaries

- Django `TestCase` and DRF `APIClient` cover backend behavior.
- Playwright covers browser workflows under `frontend/e2e/`.
- Playwright uses the isolated PostgreSQL database configured by
  `E2E_POSTGRES_*`.
- CI runs the backend test suite, frontend type checking/build, and backend and
  frontend Docker image builds.
