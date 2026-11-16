# Core backend verification

The `add-core-backend` implementation was verified with:

- `uv sync --locked`: dependency installation and application import passed.
- `uv run pytest -q`: 112 tests passed against PostgreSQL 16, including unit,
  permission-matrix, lifecycle, concurrent authentication, and end-to-end tests.
- After enabling the dedicated JSON request-log handler, the eight foundation and
  configuration tests passed again, including error/log secret-redaction checks.
- `uv run ruff check .` and `uv run ruff format --check .`: passed.
- `uv run alembic upgrade head` on initially empty development/test databases and
  `uv run alembic check`: passed, with no pending model/schema changes.
- Runtime privilege tests deny business DELETE/TRUNCATE, audit UPDATE/DELETE/TRUNCATE,
  and schema creation while allowing required application and cleanup operations.
- Local Compose image build, PostgreSQL/runtime-role setup, and API readiness passed.
- `uv run python scripts/check-proxy.py`: readiness, UUID tracing, the 12 MB request
  limit, and login rate-limit JSON responses passed through nginx.
- `nginx -t` passed for both local HTTP configuration and the TLS listener using a
  temporary test certificate in an ephemeral container with no published ports.
- OpenAPI/database inventory confirmed 20 core API paths and no POS routes/tables.
- `openspec validate add-core-backend --strict`: passed.

The initial database contains no automatically seeded operator password. Follow the
interactive Supervisor bootstrap instructions in README to create the first local
account. Development SMS verification accepts `123`; production needs a configured
HTTPS provider or gateway and actual handset delivery verification before release.

The core implementation intentionally leaves POS device counts, open-task guards,
notifications, imports, transaction history, visits, and POS reports for the next
change. No frontend or mobile-client code is included. The change is ready for review;
it has not been archived or deployed to production.
