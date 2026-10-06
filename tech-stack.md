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
- `whatsapp/` owns the isolated GREEN-API transport, configuration validation,
  test-send command, and asynchronous send task. It is not connected to ticket
  creation or automatic AI responses.
- `helpdesk/` owns project settings, URL routing, Celery configuration, and
  health checks.

## Authentication and security

The React application uses expiring Django REST Knox bearer tokens stored in
per-tab `sessionStorage`; its API client omits browser cookies and sends the
current tab's token. Logout revokes only that token. Django session
authentication and CSRF protection remain available for legacy clients and the
Django admin. CORS and CSRF trusted origins are configured for the local Vite
ports. Production throttling and Redis-backed caching are enabled when
`DJANGO_ENV=production`.

Email intake can run AI auto-resolution through Celery. Admins control the
database-backed master switch, email/WhatsApp channels, simulation mode, and
minimum similarity/confidence threshold from the Admin Panel; workers read the
current values when processing and immediately before sending. Defaults are
disabled and simulation-only, with an 85% threshold. The worker compares new
tickets with cached embeddings from resolved tickets having meaningful,
human-authored replies, then stores match scores, selected match, confidence,
response, decision, channel, and delivery outcome in the audit log. Sensitive
or uncertain tickets and weak matches remain for agent review. Email delivery
uses the configured Django email backend. WhatsApp auto-send remains
unavailable for generated text because the existing Meta integration only
sends a fixed approved template; enabled WhatsApp cases are explicitly recorded
as template-restricted and sent for review. Delivery uses a committed sending
state and does not retry uncertain email outcomes, preferring a possible missed
send that agents can review over duplicate customer messages.

Attachments are exposed through ticket-scoped authenticated endpoints. AI input
is sanitized before provider requests, and AI calls are recorded in the
`AILog` model without storing unsanitized prompts.

GREEN-API settings are loaded server-side from the existing repository-root
`.env`. Use `python manage.py send_whatsapp_test` to check instance state
without sending. A real test message requires `--phone`, `--message`, and the
explicit `--confirm-send` flag. The `whatsapp.tasks.send_whatsapp_message_task`
Celery task checks authorization before sending. When
`WHATSAPP_PROVIDER=green_api`, opted-in ticket resolution notifications use
GREEN-API after checking instance authorization; `WHATSAPP_PROVIDER=meta`
continues to use the Meta template sender. Credentials are never sent to the
React application or included in provider error logs.

## AI and retrieval

OpenAI provides ticket classification, summaries, and suggested replies through
the Responses API. Ollama provides knowledge-base embeddings with
`nomic-embed-text`, validated at 768 dimensions to match the existing pgvector
column. The existing deterministic hash embedding remains available only when
`EMBEDDING_PROVIDER=local` is selected explicitly. Retrieval filters both
pgvector and JSON vectors by provider-qualified model metadata, so vectors from
different embedding spaces are never compared.

The AI flow is:

1. Load ticket conversation content.
2. Sanitize prompt content.
3. Retrieve knowledge-base chunks with the matching Ollama embedding model.
4. Send structured context to OpenAI.
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
