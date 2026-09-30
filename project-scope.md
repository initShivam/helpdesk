# Product Scope

## Problem

Support teams receive a large volume of email and spend significant time
manually classifying, routing, and answering requests. Helpdesk provides a
shared ticket workflow with optional AI assistance so agents can respond faster
without losing human review.

## Product capabilities

- Convert inbound support email into tickets and messages.
- Track ticket status, category, assignment, priority, and conversation history.
- Search, filter, and sort tickets.
- Store and download message attachments securely.
- Index Markdown and PDF knowledge-base documents.
- Retrieve relevant knowledge-base context for AI requests.
- Generate, edit, and accept suggested replies as an agent-controlled action.
- Provide administrator-only agent management.

## Ticket behavior

### Statuses

- Open
- Resolved
- Closed

### Categories

- General Question
- Technical Question
- Refund Request

### Roles

- **Admin** - manages agent accounts and has administrative access.
- **Agent** - views and manages tickets and can review AI suggestions.

## User experience

The frontend provides:

- Login and session-aware protected routes.
- Ticket list with search, filters, and ordering controls.
- Ticket detail with messages, attachments, status actions, and replies.
- AI suggestion controls with loading, editing, and acceptance states.
- Administrator agent management.

## Scope boundaries

The following are not part of the completed Phases 0-4:

- Production monitoring, audit logs, backup drills, and deployment automation (Phase 5).
- Kubernetes or Helm deployment (Phase 5).

## Deployment decisions

The hosting provider is Render. The API, workers, database, and Redis are configured for Singapore; Render hosts static sites on its global CDN. Remaining operational decisions are:

- S3-compatible media bucket provider, region, and credential policy (the code and Blueprint support private S3-compatible storage).
- Production monitoring/alert delivery and ownership.
- Gmail credential/token rotation policy.
- Backup retention, recovery point objective, and recovery time objective.
- CI/CD and production secret-management policy.
