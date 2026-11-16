# Tasks

## 1. Project foundation

- [x] 1.1 Scaffold Python 3.12, uv dependencies and lockfile, the application factory, feature directories, and Ruff configuration; verify `uv sync --locked` and an app import succeed.
- [x] 1.2 Add environment settings, `.env.example`, production documentation restrictions, and exact-origin credentialed CORS for the web frontend; verify missing secrets fail startup and allowed/disallowed origins, CSRF preflights, and production docs behave as specified.
- [x] 1.3 Add PostgreSQL 16, API Dockerfile, Compose, and owner/runtime role provisioning without committed credentials; verify fresh local startup and document setup, server, and shutdown commands in README.
- [x] 1.4 Establish pytest, pytest-asyncio, httpx clients, isolated PostgreSQL fixtures, and controllable time; verify a smoke test runs against a disposable real database and document the test database safety boundary.

## 2. Shared API behavior

- [x] 2.1 Implement domain errors, exception handlers, request IDs, and structured sanitized logging; verify malformed JSON, validation, missing routes, unexpected failures, valid/invalid request IDs, and secret redaction through HTTP tests.
- [x] 2.2 Implement pagination, sorting allowlists, and response envelopes; verify invalid bounds and unknown sort fields return 422 and stable pagination handles tied values.
- [x] 2.3 Implement digit, Persian text, mobile, national-code, and search normalization; verify unit tests cover international prefixes, Persian/Arabic digits, checksum failures, repeated-digit codes, and whitespace variants.
- [x] 2.4 Implement native UTC storage, configured business-day helpers, shared Jalali date/date-time parsing and serialization, and public liveness/readiness; verify Persian-digit input, leap dates, invalid dates/missing offsets, timezone-boundary round trips, and readiness failure while liveness stays 200.
- [x] 2.5 Document shared errors, pagination, Jalali formats, protocol-date exceptions, timezone, configuration, and health paths; verify OpenAPI examples describe Jalali strings accurately and HTTP tests agree.

## 3. Database schema and audit infrastructure

- [x] 3.1 Define base/soft-delete metadata and six core tables including login challenges, keyed code digests, delivery state, attempt/deadline metadata, named constraints, partial unique indexes, actor references, and trigram search; review the initial migration and verify upgrade plus challenge uniqueness on real PostgreSQL.
- [x] 3.2 Add runtime grants, audit sequence access, token/challenge cleanup privileges, and extension setup; verify the runtime role cannot delete business rows or update/delete audit rows but can perform permitted operations.
- [x] 3.3 Implement transaction ownership and the explicit security-rejection outcome; verify ordinary errors roll back while an authorized commit-on-rejection path persists its state before returning an HTTP error.
- [x] 3.4 Implement the shared audit helper with changed-field filtering, request metadata, and removal of passwords, tokens, SMS codes/digests, CSRF secrets, and provider credentials; verify mutation/audit atomicity and masked failed-login/SMS records using separate read sessions.
- [x] 3.5 Document migration credentials, role provisioning, grants, bootstrap ordering, and non-destructive rollback; verify the documented fresh-database setup path works.

## 4. Authentication and authorization

- [x] 4.1 Implement password policy, argon2id hashing/rehash, strict JWT verification, and hashed opaque refresh tokens; verify policy boundaries, expiry, invalid signatures/algorithms, and absence of raw tokens in stored rows.
- [x] 4.2 Implement and document `create-supervisor` with interactive password entry and `--force`; verify initial creation, repeated-run refusal, forced creation, and atomic bootstrap audit.
- [x] 4.3 Implement first-factor login with normalized mobile, dummy verification, row locking, lockout, and challenge creation; verify five password failures persist, lock expiry, counter reset, disabled accounts, concurrency, and a 202 response with no tokens or successful-login audit before SMS verification.
- [x] 4.4 Implement refresh-cookie rotation and reuse revocation under consistent user/token locking; verify expiry, disabled users, sequential reuse, cookie replacement, no raw refresh tokens in JSON/URLs, and concurrent refresh, checking revocations after 401 responses.
- [x] 4.5 Implement current-user loading, role guards, Scope, `/auth/me`, and forced-password-change restrictions; verify stale role/branch claims cannot override stored permissions and disabled users lose access immediately.
- [x] 4.6 Implement password change and authenticated idempotent logout using owned refresh cookies; verify current-cookie session retention, all-session revocation without it, pending-challenge invalidation, current-password validation, cookie clearing, applicable CSRF checks, and forced-change restrictions clearing on success.
- [x] 4.7 Implement `purge-tokens` for old refresh tokens and expired/consumed/invalidated challenges and document daily usage; verify retention cutoffs preserve current sessions/challenges and secrets never appear in responses, logs, or audit.
- [x] 4.8 Implement the synchronous SMS adapter contract, dev no-send adapter accepting `123`, keyed code verification, non-dev random six-digit codes, timeout handling, and environment guards; verify no external calls in dev/tests, fake-provider failure paths, and startup refusal for fixed mode or missing adapters outside dev; document configuration and the production delivery gate.
- [x] 4.9 Implement `/auth/verify-sms` with five-minute expiry, five attempts, current account/mobile checks, atomic consumption, and session creation only after success; verify wrong/expired/used codes, persisted failure counters, concurrent verification, Jalali response dates, and audit outcomes.
- [x] 4.10 Implement `/auth/resend-sms`, pending/sent/failed delivery state, replacement challenge IDs, and a per-user 60-second cooldown across resend/login; verify prior-ID invalidation, carried attempt/deadline limits, no authentication after delivery failure/crash, concurrent sends, and cooldown-bypass rejection.
- [x] 4.11 Implement browser cookie flags, in-memory access-token contract, `/auth/csrf`, signed session-bound CSRF checks, and exact Origin enforcement; verify hostile/missing origins and missing/wrong CSRF rejection, no-store CSRF retrieval, cookie path/host/SameSite/HttpOnly/Secure settings, and refresh after frontend reload.
- [x] 4.12 Document the web password-to-SMS flow, verify/resend requests, dev code `123`, session reload/refresh/logout, error codes, and SMS limits; verify examples against the HTTP tests and explicitly exclude frontend/mobile implementation.

## 5. Organization management

- [x] 5.1 Implement city schemas, services, and routes with normalization, uniqueness, filtering, and soft deletion; verify all-role reads, Supervisor-only writes, duplicate conflicts, and `city_has_branches`.
- [x] 5.2 Implement branch CRUD, normalized codes, derived manager, city identity, employee count, and city moves; verify uniqueness within cities, one-manager behavior, deactivation, and `branch_in_use` without creating POS placeholders.
- [x] 5.3 Apply branch scope to detail, lists, counts, and filters; verify cross-branch IDs return 404, conflicting manager filters return 403, and employee reads expose only their branch.
- [x] 5.4 Document organization APIs, sort allowlists, inactive-filter defaults, and soft-delete behavior; verify examples against tests, including inactive dependents and retained historical references.

## 6. User management

- [x] 6.1 Implement user creation, update, list/detail, validated identifiers, generated temporary passwords, and normalized search; verify secret-free representations, one-time password return, role/branch checks, and identity reuse after soft deletion.
- [x] 6.2 Implement activate, deactivate, reset-password, and soft-delete operations with refresh-token revocation, pending-SMS invalidation, and audit; verify immediate account blocking, reset unlock, forced changes, mobile-change revocation, and old-mobile challenge rejection.
- [x] 6.3 Implement self-modification guards and serialized last-active-Supervisor protection; verify concurrent administrative operations leave an active Supervisor and return stable lifecycle conflicts.
- [x] 6.4 Enforce manager uniqueness and staff visibility with database-backed concurrency protection; verify simultaneous promotions cannot create two managers and employee list/detail requests are forbidden.
- [x] 6.5 Document user endpoints, lifecycle conflicts, password handling, and the POS follow-up requirements for open-task guards and branch device counts; verify the documented core contract matches tests.

## 7. Audit retrieval and deployed behavior

- [x] 7.1 Implement Supervisor-only audit retrieval with Jalali business-day filters, newest-first ordering, and pagination; verify UTC interval conversion, Jalali occurrence and before/after date output, denied roles, secret exclusion, and reads producing no additional audit entries.
- [x] 7.2 Configure nginx request limits, login rate limits, UUID tracing, JSON error bodies, and trusted forwarding; verify `nginx -t` and proxy-path smoke tests for 413, 429, and matching request IDs, and document local HTTP versus production TLS setup.
- [x] 7.3 Verify an end-to-end workflow from fresh migrations/bootstrap through each role's password-plus-SMS login, browser cookies/CSRF, reload/refresh, forced change, scoped organization reads, reset invalidation, and Jalali audit review; run the complete PostgreSQL suite plus `uv run ruff check .` and `uv run ruff format --check .`.
- [x] 7.4 Verify the README setup commands, Compose health checks, production docs restriction, runtime privileges, and no POS routes/tables; record the final check results and remaining POS handoff items.
