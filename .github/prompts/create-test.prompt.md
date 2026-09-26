---
agent: 'agent'
description: 'Create focused automated tests for a requested Helpdesk behavior'
---

# Create tests

Create tests for the requested behavior: ${input:Describe the behavior and expected outcomes}

Before editing, inspect the implementation and nearby tests to identify the existing
test framework, conventions, fixtures, and the narrowest relevant test command. Add
tests only for the requested behavior; do not change application code, dependencies,
or unrelated files. If existing behavior appears broken, report the finding rather
than changing production code to make the test pass.

## Test placement and conventions

- Backend tests belong in the relevant Django app's existing `tests*.py` files. Use
  Django `TestCase` and DRF's `APIClient` where appropriate, matching neighboring
  tests.
- Browser end-to-end tests belong in `frontend/e2e/` as Playwright `*.spec.ts`
  files. Use `@playwright/test` and the configured web servers; avoid duplicating
  coverage that is better expressed as a focused backend or component test.
- Cover expected results and meaningful failure/permission cases. Keep tests
  deterministic, isolated, and independent of real mailboxes, external services,
  production data, or machine-specific state. Mock external boundaries when needed.
- Prefer user-visible behavior and public API contracts over implementation details.
  Do not add arbitrary sleeps, skip tests, weaken assertions, or use `.only`.
- Do not create tests beyond the requested scope. Ask for clarification only when
  the behavior or expected result cannot be determined from the request and code.

## Database safety and validation

- For Playwright, use the existing `frontend/playwright.config.ts` setup. It sets
  `HELPDESK_E2E=1` and connects to the isolated PostgreSQL E2E database configured
  by `E2E_POSTGRES_*`; never switch E2E to SQLite or point it at the development
  database.
- Never drop, truncate, or otherwise reset a shared or development database. Django
  test-runner database lifecycle and Playwright's configured E2E database are the
  supported isolation mechanisms.
- Run the narrowest relevant test command after writing tests:
  - Backend: from `backend/`, run `python manage.py test <app.tests_module>` (or the
    specific test class/method).
  - Playwright: from `frontend/`, run `npm run e2e -- <spec-file-or-grep>`.
- If validation cannot run because of an environment or service prerequisite, leave
  the tests intact and clearly report the blocker. Finish with the files changed,
  behaviors covered, and validation result.
