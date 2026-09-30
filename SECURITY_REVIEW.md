# Phase 5 security review

This is a source/configuration review against OWASP Top 10 (2021), not a penetration test or an organization-specific compliance approval. Review the release configuration again after choosing the production provider and edge network.

| Area | Repository controls and findings | Follow-up |
| --- | --- | --- |
| A01 Broken access control | Ticket APIs require authenticated agent/admin roles; user administration and knowledge-base management are admin-only; attachment downloads are scoped to the requested ticket. | Verify business-specific ticket visibility and admin role assignment in the target identity process. |
| A02 Cryptographic failures | Production requires an explicit Django secret, HTTPS, secure session/CSRF cookies, HSTS, and same-origin referrer policy. Compose does not publish DB/Redis and binds UI/monitoring ports to loopback. | Terminate TLS at the selected trusted ingress, encrypt volumes/backups, and rotate any credentials previously committed in Git history. |
| A03 Injection | Django ORM is used for application queries; health SQL is a fixed `SELECT 1`. React renders text through normal React escaping. Uploaded knowledge documents now have file type, size, page, and extracted-text limits. | Keep AI prompt-injection defenses under review; retrieval content is untrusted input. |
| A04 Insecure design | AI operations are asynchronous in production, use bounded retry, and have a configurable per-user request throttle. Audit records avoid message bodies. | Define data retention, least-privilege service accounts, and recovery objectives for production. |
| A05 Security misconfiguration | Production rejects DEBUG, wildcard/empty allowed hosts, placeholder secrets, and non-HTTPS frontend origins. Development CORS origins are restricted to localhost. | Restrict `/metrics` to the internal network at deployment and configure alert delivery. |
| A06 Vulnerable and outdated components | Python application dependencies are pinned; monitoring images and Celery exporter use explicit version tags. Docker base images are version-family tags, not digest-pinned. | Run dependency/container vulnerability scans in the release pipeline and schedule image/dependency updates. |
| A07 Identification and authentication failures | Django password validators, CSRF-protected login, session rotation, configurable server-side expiry, logout revocation, and production login throttling are configured. | Use the production secret manager and review account recovery/MFA policy with the deployment owner. |
| A08 Software and data integrity failures | CI runs backend tests, frontend typecheck/build, Playwright E2E, and Docker image builds. | Pin GitHub Actions to immutable commit SHAs and add image provenance/signing before publishing. |
| A09 Security logging and monitoring failures | Prometheus metrics, Grafana data-source provisioning, target-down rules, and success-only login/logout/status/AI acceptance audit events are configured. | Route alerts to an owner; decide audit retention and monitor unauthorized access attempts in the host/edge logs. |
| A10 Server-side request forgery | User-supplied document content is not used as a fetch URL; outbound AI calls use a fixed provider endpoint. | Restrict production egress to required providers and Gmail endpoints. |

## Verification performed

- `python manage.py check --deploy` with production-only environment values: passed.
- Backend suite: 68 tests passed, including knowledge-base upload validation coverage.
- Frontend TypeScript check and production build: passed (the bundler reports a 739 KB JavaScript chunk).
- `docker compose config` for development and production: passed with the required production Grafana password supplied.
- Backup/restore shell syntax: passed. A live restore, image build, E2E browser run, and penetration test were not possible here because the Docker daemon is unavailable.
