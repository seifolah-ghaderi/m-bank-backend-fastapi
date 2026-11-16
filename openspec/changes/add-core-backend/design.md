# Design

## Context

See `proposal.md` for motivation and the five capability specs for behavioral contracts. Only requirements documents and OpenSpec configuration exist today. The Phase 1 source specifies Python 3.12, FastAPI, SQLAlchemy 2 async, PostgreSQL 16, Pydantic v2, uv, and Ruff. Approved revisions make the web frontend the phase's client, require Jalali API dates, and add SMS as the second login factor; these supersede the original UTC-response and password-only contracts. Authentication references organization tables and needs audit recording immediately.

## Goals / Non-Goals

**Goals:** Deliver a runnable core with enforced authorization, durable security state, database-enforced constraints, and real-database tests. Keep module boundaries simple enough for a small application.

**Non-goals:** POS models or placeholder POS APIs, notification infrastructure, a generic task engine, repositories, domain classes, external identity providers, UI, Redis, or Celery. POS date-history and locking ambiguities are deferred to the POS design because no such operations exist here.

## Decisions

### 1. One application with feature services

Use `app/main.py` with an app factory, `app/core/` for settings, sessions, security, permissions, normalization, errors, pagination, and audit helpers, `app/models/` and `app/schemas/`, and `app/features/{auth,org,users,audit}/`. Routers validate requests and serialize schemas; async services enforce rules and raise domain errors. Shared operations live in core or models, avoiding cross-feature service imports. A repository layer adds little value at this scale.

Use Uvicorn with the app factory. Document `uv run uvicorn app.main:create_app --factory --reload`, `uv sync`, migrations, tests, and Ruff commands once implemented. Commit the dependency lockfile; `requirement.txt` remains a requirements document.

### 2. Build the six-table schema together

Create `cities`, `branches`, `users`, `refresh_tokens`, `login_challenges`, and `audit_logs` in the initial reviewed Alembic migration. Use UUIDv7 for entity IDs and the source's bigserial audit ID. Define named checks and foreign keys, timezone-aware timestamps, actor metadata, soft-deletion fields, partial unique indexes for live identities/names, and one non-deleted manager per branch. Normalize names consistently before persistence and search; use `pg_trgm` for staff-name search.

Challenges contain a random unguessable ID, user ID, bound normalized mobile, keyed code digest, creation/expiry/last-send times, failed-attempt count, consumption/invalidation times, and delivery state. Use a partial unique index for one non-consumed, non-invalidated challenge per user; explicitly invalidate expired rows before replacement. Track send cooldown across replacements while holding the user lock. Short codes use HMAC with an environment secret rather than an unkeyed digest; never persist plaintext. No Redis or generic notification tables are needed.

Create the circular users/created-by foreign keys after all tables exist. Bootstrap allows nullable actor fields, flushes the Supervisor, and records bootstrap in the same transaction. No account is inserted by migrations. Future POS tables and guards arrive in a later migration; do not introduce empty tables or misleading zero-valued device counts.

### 3. Transaction outcomes include security rejections

Ordinary request transactions commit successful actions plus audit, and roll back business failures. Services flush but never commit. A small explicit result type represents authentication outcomes that reject a request after a required state change. The router passes that result through the transaction boundary, which commits the counter/audit/revocation before raising the mapped HTTP error. Unexpected exceptions still roll back. This keeps transaction ownership in one place and avoids committing arbitrary domain errors.

Lock the user for login counters, SMS challenges, and token rotation/revocation. Acquire locks consistently: user before that user's challenge or token rows. Re-read state after acquiring locks. Test concurrent refresh, verification, resend, and lockout using separate database connections. Do not use independent background audit writes for successful mutations, since they break atomicity.

### 4. Authentication sessions and current authorization

Use argon2id with rehash-on-login, HS256 JWT access tokens, and 256-bit random opaque refresh tokens stored as SHA-256 hashes. Decode with an explicit algorithm allowlist and validate expiry and required claims. Access claims contain `sub`, `role`, `branch_id`, `jti`, `iat`, and `exp`; the database user determines permissions on every protected request. Use dummy password verification for unknown mobile numbers to limit timing differences.

Password login only creates an SMS challenge and returns 202. `POST /api/v1/auth/verify-sms` takes `challenge_id` and `code`; only successful single-use verification updates last-login time, audits login success, and issues access/refresh credentials. Recheck current account eligibility and mobile binding under the user lock. Password reset/change, mobile change, deactivation, and soft deletion invalidate pending challenges; never let a challenge sent to an old mobile complete login.

`POST /api/v1/auth/resend-sms` replaces the challenge with a new ID and code, invalidating the previous ID. Carry forward failed attempts and original five-minute expiry. Enforce a per-user 60-second send cooldown across both resend and repeated password-login requests. An expired/exhausted challenge requires password login again. Verification permits five incorrect attempts; persist attempts, invalidation, and sanitized audit before returning an error. Returning a fresh ID also makes old development challenges unusable even though their code is always `123`.

Use a small synchronous SMS adapter with bounded network timeouts and a delivery result; no background queue. Persist pending challenge state, perform delivery, then mark sent/failed and audit the result through an explicit delivery transaction boundary. Never hold a database lock across the provider call. Verification/resend require a sent, currently active challenge. If sending or finalization fails, issue no session; an unsent/failed challenge cannot authenticate. This documents the external-I/O exception to one-transaction-per-request; an SMS cannot be rolled back. A crash leaves a pending challenge that cannot verify and eventually expires.

`ENVIRONMENT=dev` selects an adapter that makes no external calls and verifies `123`, while retaining the full challenge lifecycle. Staging/production require a real configured adapter and cryptographically random six-digit codes. Reject fixed-code mode outside dev and missing adapter configuration at startup. Document provider credentials, sender/template configuration, timeout, `SMS_CODE_TTL_SECONDS=300`, `SMS_MAX_ATTEMPTS=5`, `SMS_RESEND_COOLDOWN_SECONDS=60`, and the code-digest secret in `.env.example` without real secrets. Provider selection/configuration is a pre-production integration step; record a production readiness gate until real delivery is tested.

The web frontend receives an access token in JSON and holds it in memory. Issue opaque refresh tokens only via a host-only HttpOnly SameSite=Strict cookie scoped to `/api/v1/auth`; use Secure outside local HTTP development. Prefer serving frontend and API on the same site; exact configured origins support credentialed CORS, and cross-site deployment is outside this phase. No refresh token is accepted from JSON or query parameters.

Provide `GET /api/v1/auth/csrf` to return a session-bound signed CSRF token for a valid cookie, with no-store caching and allowed-Origin enforcement. Require that token in `X-CSRF-Token` plus allowed Origin for cookie-based refresh, logout, and password change. Return a fresh CSRF token with each rotated session; the frontend can fetch it again after reload. Token verification binds the CSRF value to the presented refresh credential without disclosing it. Do not rely on CORS alone as CSRF protection.

Token refresh remains available to active forced-change accounts, granting no additional application permissions. Change-password retains the caller's valid refresh-cookie session and revokes others; without that cookie it revokes all refresh sessions. Logout requires access authentication, clears the cookie, and does not revoke another user's session. Apply Origin/CSRF checks before idempotent logout handling when a cookie is present. Access tokens remain valid until expiry after ordinary logout/password change; database checks immediately block deactivated/deleted accounts.

### 5. Scope and lifecycle guards are centralized

Resolve a Scope containing current role, branch, and user ID. Apply it to both data queries and count queries. Employees use `/auth/me` for user details; this follows section 7 and the API catalog despite the broader self-read wording in the permission matrix. Disallowed actions return 403; inaccessible IDs return 404. Branch Manager filters cannot select a different branch.

Enforce uniqueness in PostgreSQL as the final concurrency guard, mapping known constraint failures to stable errors. Serialize operations affecting active Supervisor availability with a transaction-level advisory lock, then recheck the active count. Self-modification guards run first. Merely counting Supervisors without serialization can remove all administrators concurrently.

Lists default to name ordering for organization, descending creation time for users, and descending occurrence time for audit, always with an ID tie-breaker. Explicit `include_inactive=false` serves lookups; omitted values include inactive records for Supervisors and exclude them for other roles. Each endpoint publishes its sort allowlist. Ordinary queries exclude soft-deleted records.

### 6. Enforce privileges separately from schema ownership

Use a migration/owner database role for migrations and extension creation and a separate non-owner runtime role. Grant runtime SELECT/INSERT/UPDATE on core business tables and challenges, SELECT/INSERT on audit with required sequence access, and token/challenge DELETE for retention cleanup. Never grant business DELETE or audit UPDATE/DELETE. Restrict runtime schema creation and inherited/public privileges. Role provisioning is an operator/deployment step with environment-injected credentials, not hard-coded migration secrets.

### 7. Run and verify locally as deployed

Compose runs api, PostgreSQL, and nginx, with persistent database storage. Nginx terminates production HTTPS, enforces the 12 MB limit and ten login requests/minute/IP, and returns API-shaped limit errors with UUID request IDs. Forward only trusted proxy metadata. Define an explicit nginx configuration/template strategy for generated UUIDs and JSON error bodies; verify it through the proxy rather than assuming default nginx errors comply. Local development may use HTTP.

Use isolated PostgreSQL test databases, httpx AsyncClient, pytest-asyncio, and deterministic clock control. Unit tests cover normalization, Jalali leap years/round trips, and password policy; integration tests cover migrations, constraints, permissions, transaction outcomes, cookies/CSRF, and concurrency. Inject fake SMS adapters for success, failure, and timeout; no test sends a real SMS. Exercise runtime-role privileges separately from the schema-owner test connection. No numeric coverage target is invented.

### 8. Jalali at every business API boundary

Persist native PostgreSQL dates and UTC timestamptz values. Add one shared conversion module and Pydantic date/date-time types that parse Jalali inputs, normalize Persian/Arabic digits, validate real calendar dates, and serialize ASCII strings. Dates use `YYYY/MM/DD`; date-times use `YYYY/MM/DDTHH:mm:ss[.ffffff]±HH:MM`, with response offsets determined by `APP_TIMEZONE` (default Tehran). Reject missing offsets and invalid Jalali dates with 422; do not label these strings ISO 8601 or silently interpret Gregorian values.

Apply the types to every entity's date metadata, auth response date-times, filters, and audit before/after date values. Audit retrieval converts typed date values using the entity/schema field mapping, never arbitrary strings or identifiers. Date-only audit filters include the whole local day: convert from-date midnight and the exclusive midnight after to-date into UTC query bounds. Keep chronological comparisons, sorting, expiry, and database queries on native values, never formatted Jalali strings. JWT NumericDate claims, duration seconds, HTTP Date/cookie Expires, and operational log timestamps retain their standard forms. This avoids implementing calendar arithmetic throughout services while giving the web client a consistent Persian-calendar contract.

## Risks / Trade-offs

- Security failure updates can be lost on rollback → test persisted state after the HTTP error through a separate session.
- Broadening core into all Phase 1 work → explicitly defer device counts, open-visit guards, notifications, and reports; document the handoff.
- Soft-deleted identity reuse can confuse historical output → retain foreign keys and resolve historical actors without applying ordinary active-row filters.
- Runtime role accidentally owns tables → provision separate credentials and test forbidden SQL operations.
- JWT logout does not immediately revoke access → retain the specified short expiry and database account-state checks; per-session access revocation would be a separate requirement.
- Proxy error formatting and request IDs differ from application behavior → include deployed-path smoke tests and avoid logging request bodies or authorization headers.
- SMS delivery is not transactional → persist delivery state, fail closed on uncertain delivery/finalization, and require production provider delivery verification before release.
- Fixed codes could escape development → reject incompatible environment/configuration combinations at startup and test staging/production rejection.
- Custom Jalali strings are not native browser ISO dates → document exact formats, schema examples, timezone behavior, and leap-date errors for the web frontend.
- Cookie refresh could be targeted by cross-origin requests → enforce SameSite, explicit Origin and session-bound CSRF checks, with browser-path tests.

## Migration Plan

1. Provision PostgreSQL 16 and migration/runtime roles; install `pg_trgm` and `btree_gist` using the privileged setup path.
2. Apply the initial migration with owner credentials and verify grants using the runtime role.
3. Configure calendar, web origin, cookie/CSRF secrets, and SMS mode. Start the service, run readiness, bootstrap the Supervisor interactively, and smoke-test password/SMS login, cookie refresh, Jalali output, and organization CRUD. Local dev uses `123`; production rollout requires real provider delivery verification.
4. Before deployment, run migrations and the complete PostgreSQL-backed suite against a fresh database, plus nginx smoke tests.
5. Roll back a failed initial deployment by stopping the service and retaining the database. Destructive migration downgrade is limited to disposable environments; production recovery uses backups or forward fixes to preserve records.
