# Helpdesk System – Architecture Overview

## Revised Phase Structure & Dependencies

| Phase | Description | Depends On |
|------|-------------|-------------|
| **Phase 0 – Foundation** | Project scaffolding, CI/CD, core services, shared utilities (logging, config, health checks). | – |
| **Phase 1 – Authentication & RBAC** | User & agent accounts, role definitions (ADMIN, AGENT), JWT/OAuth flow, permission checks in all backend endpoints. | Phase 0 |
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
2. **Phase 1 – Authentication & RBAC** – user/role models, JWT/OAuth, admin UI.
3. **Phase 2 – Ticket Management** – ticket model, CRUD, UI.
4. **Phase 3 – AI Classification & Summary** – AI pipeline, confidence fields.
5. **Phase 4 – Knowledge‑Base & RAG** – vector store abstraction, configurable embedding model.
6. **Phase 5 – AI Suggested Replies** – `AISuggestion` model, suggestion workflow.
7. **Phase 6 – Email Ingestion** – email parser, attachment handling.
8. **Phase 7 – Dashboard & Analytics** – ticket view, AI metrics, optional Prometheus/Grafana.
9. **Phase 8 – Production Hardening** – Helm charts, tracing, security, optional enterprise infra.

---

*This document captures the architectural decisions and roadmap. Further code will be added in subsequent phases.*
