# Core verification

Run `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, and
`uv run alembic check`. Tests use a dedicated real PostgreSQL 16 instance with a
database name ending `_test`; they never use the application DATABASE_URL. See
README for the disposable container command. Database fixtures truncate only that
dedicated database, and migrations receive independent test configuration.

| Contract | Regression coverage |
| --- | --- |
| Settings, CORS, production restrictions | `test_config.py` |
| Errors, tracing, redaction, liveness/readiness | `test_foundation.py` |
| Stable scoped lists and bounds | `test_pagination.py` |
| Iranian normalization/checksums | `test_text.py` |
| Jalali leap dates, offsets, business-day boundaries | `test_dates.py` |
| Fresh schema, circular actor FKs, unique manager/challenge, DB privileges | `test_schema.py` |
| Rollback versus persistent security rejection; atomic audit | `test_transactions.py` |
| Password policy, hashing, JWT expiry/signature/algorithm | `test_security.py` |
| Password/SMS flow, expiry/attempts, resend, refresh reuse, forced change | `test_auth.py` |
| Concurrent login/verification/refresh, delivery failure, CSRF, adapter | `test_auth.py`, `test_auth_edges.py` |
| Bootstrap, force guard, retention cleanup | `test_cli.py` |
| CRUD, live uniqueness, soft deletion, branch boundaries, role/lifecycle guards | `test_org_users.py` |
| Bootstrap through all roles; unauthenticated/forced-change endpoint matrix | `test_workflow.py` |

Concurrency tests use separate request transactions/connections. Security-state tests
read persisted counters and revocations after rejected HTTP requests. Injected clocks
avoid waiting for expiry; fake providers avoid real SMS or provider credentials.

With local Compose running, `uv run python scripts/check-proxy.py` verifies readiness,
UUID tracing, the 12 MB limit, and nginx login throttling. It intentionally consumes
the local login rate-limit allowance. `docker compose exec -T nginx nginx -t` validates
the mounted proxy configuration. Application tests and runtime privilege tests are
separate, so using a schema-owner fixture cannot conceal missing runtime restrictions.

POS schema/privilege, registry/history/export, import/recovery, transaction/performance,
visit/concurrency, report, and end-to-end tests are in `test_pos_*.py`.
Optional local-only tools `scripts/profile-pos.py` and `scripts/check-pos.py` are
excluded from required acceptance at the user's request. They use synthetic data;
the profile refuses any database name except `crm_pos_scale_test`. Production handset delivery
needs separate operational verification; fake-provider tests do not establish it.
