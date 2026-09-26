# Helpdesk

Helpdesk is a Django and React application for turning support email into
trackable tickets. Agents can manage tickets, review messages and attachments,
retrieve knowledge-base context, and approve AI-generated reply drafts.

## Documentation

- [Product scope](project-scope.md) - product goals, user roles, ticket behavior,
  and decisions still requiring product input.
- [Technical stack](tech-stack.md) - current architecture, services, data
  boundaries, and deployment responsibilities.
- [Implementation plan](implementation-plan.md) - phase requirements, status,
  milestones, and remaining roadmap work.
- [Running the application](RUNNING.md) - Docker, local development, email
  polling, and end-to-end test commands.

## Repository layout

```text
backend/                 Django project, APIs, workers, migrations
frontend/                React/Vite application and Playwright tests
.github/workflows/       GitHub Actions CI
docker-compose.yml       Local multi-service environment
.env.example             Environment variable reference
```

## Branch strategy

`master` is the protected integration branch. Feature work uses short-lived
branches named `feature/<scope>` or `fix/<scope>` and is merged through pull
requests after CI passes. The `dev` branch is used for shared pre-release
integration when staging validation is required.

## Current status

Phases 0 through 3 in [implementation-plan.md](implementation-plan.md) are
implemented and validated. Phase 4 and Phase 5 remain roadmap work.

Start with [RUNNING.md](RUNNING.md) for setup instructions.
