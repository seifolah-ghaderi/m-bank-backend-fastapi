# Proposal

## Why

The repository describes Phase 1 but has no runnable backend. Establish a tested FastAPI API for the web frontend, with Persian dates, SMS two-factor authentication, and organization management, so POS management can build on real users, branch boundaries, and audit behavior.

## What Changes

- Scaffold a Python 3.12 FastAPI modular monolith with uv, async SQLAlchemy, PostgreSQL 16, Alembic, Docker Compose, Ruff, and pytest.
- Establish environment configuration, health checks, request IDs, consistent errors, pagination, normalization, and Jalali API dates/date-times with UTC database storage and Tehran business dates.
- Deliver password-then-SMS authentication, persisted single-use challenges, verification/resend endpoints, rotating refresh sessions in HttpOnly cookies, CSRF protection, lockout, forced password changes, authorization, and Supervisor bootstrap.
- Use fixed SMS code `123` without sending messages in development; require random six-digit codes and an SMS adapter outside development. Challenges expire after five minutes, allow five attempts, and have a 60-second resend cooldown.
- Deliver cities, branches, and users with validation, soft deletion, lifecycle guards, and database constraints.
- Record audited operations transactionally and provide Supervisor-only audit retrieval.
- Provide real-PostgreSQL integration tests and local operation instructions.
- Defer POS tables, device counts, open-visit guards, notifications, imports, reports, and all later CRM modules. These belong to subsequent changes.

## Capabilities

### New Capabilities

- `api-foundation`: Web-client runtime configuration, health, API errors, pagination, request tracing, normalized inputs, and Persian date contracts.
- `user-auth`: Password plus SMS login, development verification mode, browser sessions, refresh, logout, password lifecycle, bootstrap, and request authorization.
- `organization-management`: City and branch maintenance, lookup behavior, and branch visibility.
- `user-management`: User administration, generated passwords, lifecycle protection, and role/branch constraints.
- `audit-trail`: Append-only, sanitized audit recording and Supervisor retrieval.

### Modified Capabilities

None; there are no existing capability specs.

## Impact

Introduces `app/`, `migrations/`, `tests/`, `pyproject.toml`, a lockfile, Docker and nginx configuration, `.env.example`, and run documentation during implementation. Adds `/api/v1` auth, SMS verification/resend, city, branch, user, audit, and health APIs. Requires PostgreSQL with `pg_trgm` and `btree_gist`, Jalali conversion support, and a configurable SMS adapter; no Redis, Celery, frontend implementation, mobile-client integration, or Core Banking integration. This change creates six tables, including login challenges. The approved web-client, Persian-date, and SMS requirements supersede the corresponding sections of `Bank Marketing CRM — Phase 1 Spec Core Modules & POS Management.md`; other core requirements still follow sections 2–7 and 12–14.
