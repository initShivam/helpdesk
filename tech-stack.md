# Technical Stack
 
## Authentication
- **Method:** Django JWT with database sessions (session data stored in PostgreSQL)

## Frontend
- **Framework:** React + TypeScript
- **Styling:** Tailwind CSS
- **State Management:** React Query
- **Routing:** React Router
- **Charts:** Recharts or Chart.js (for dashboard)

## Backend
- **Framework:** Django + Django REST Framework
- **AI Integration:** Gemini LLM API (stable low‑cost model)
- **Prompting:** Structured prompts with Retrieval‑Augmented Generation (RAG)
- **Safety:** AI safety filters applied before responding
- **Logging:** Store AI analysis, model name, timestamp (raw prompts omitted)
- **Knowledge Base:** Markdown / PDF internal documents
- **Embeddings:** Lightweight embedding model (e.g., `text‑embedding‑ada‑002`)
- **Vector Store:** pgvector extension in PostgreSQL
- **Email Ingestion:** Gmail/Google Workspace via IMAP polling (webhook later)
- **Attachments:** Stored separately, validated for type and size
- **Duplicate Detection:** Email `Message‑ID` + thread ID
- **Background Jobs:** Celery workers with Redis broker
- **Roles:** Admin and Agent only

## Database
- **Primary DB:** PostgreSQL (stores tickets, users, sessions, vector data, audit logs)
- **Vector Extension:** pgvector for semantic search

## Deployment & Operations
- **Containerization:** Docker (Docker Compose for local/dev)
- **Hosting:** Docker‑first; cloud provider to be decided (target India/Asia region)
- **Domain/TLS:** To be added later (localhost during development)
- **CI/CD:** GitHub Actions
- **Monitoring:** Structured Django and Celery logs (initial)
- **Testing:** Pytest for backend, React Testing Library for frontend
- **Analytics:** PostgreSQL aggregation for dashboards
- **Dashboard Refresh:** Periodic refresh (initial)
