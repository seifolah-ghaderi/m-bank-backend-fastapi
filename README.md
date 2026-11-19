# Bank Marketing CRM backend

Python 3.12 / FastAPI / PostgreSQL 16. This phase serves a web frontend and implements
organization, authentication, and POS management APIs. See [POS management](docs/pos.md)
for English XLSX headers, monthly activity imports, global rial thresholds,
Supervisor dispatch, branch assignment, and employee visits. See
[campaigns and sales](docs/marketing.md) for lead entry, campaign visits,
Supervisor verification, customer profiles and generated retention tasks. See
[CRM spreadsheet imports](docs/imports.md) for city, branch, and lead uploads.
`requirement.txt` contains product requirements, not pip dependencies.

## Local setup

Install Python 3.12, uv, Docker, and Docker Compose. From this directory:

```sh
python3 scripts/configure-local.py
uv sync --locked
docker compose up -d postgres
uv run alembic upgrade head
uv run python -m app.cli create-supervisor --mobile 09121234567 --first-name Ali --last-name Rezaei
```

The configuration script creates a mode-0600 `.env` with random independent secrets
and refuses to overwrite an existing file. Alternatively copy `.env.example` and
populate the secrets and matching database passwords yourself. Generated hexadecimal
passwords are URL-safe. Existing PostgreSQL volumes do not rerun initialization scripts.
The runtime database identity is separate from the schema owner and must not own tables.

Start the API directly during development:

```sh
uv run uvicorn app.main:create_app --factory --reload
```

Or build the containers with `docker compose up --build -d`. The proxy listens on
`http://localhost:8080`; PostgreSQL is bound only to `localhost:55432`. Stop containers
with `docker compose down` (retains database volume). Never add `--volumes` for a database
containing records you need to preserve.

## Checks

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

The Supervisor command prompts twice for a password and refuses to run again unless
`--force` is supplied. First login requires a password change. In development the
second factor is SMS code `123` without sending messages. See
[authentication](docs/authentication.md), [API contracts](docs/api.md),
[organization/users](docs/organization.md), and [database operations](docs/operations.md).
Migration commands use `MIGRATION_DATABASE_URL`; the API uses only `DATABASE_URL`.

Schedule expired token/challenge retention cleanup daily, for example:

```cron
0 3 * * * cd /absolute/path/to/repository && /absolute/path/to/uv run python -m app.cli purge-tokens
```

Replace the example paths with actual deployment paths. Never put passwords in cron
arguments. Run `uv run python scripts/check-proxy.py` after Compose startup to check
readiness, tracing, 12 MB request limits, and the ten-per-minute login IP limit.

Local Compose uses HTTP. For production, serve frontend and API on the same site;
replace the nginx listener mount with `deploy/nginx.tls-listen.conf`, mount the TLS
certificate/key at `/etc/nginx/tls/cert.pem` and `key.pem`, and publish 443 instead of
80. Set `ENVIRONMENT=production` with real HTTPS SMS configuration and exact web
origins. Verify production handset delivery before release. Do not deploy dev fixed
SMS mode. Only nginx's private `NGINX_IP` is trusted for forwarded headers. If the
default `CRM_SUBNET` conflicts with local networks, set both variables consistently.
The API has no public port; do not add a direct port without revisiting proxy trust.

### Disposable PostgreSQL tests

Start an isolated instance (test-only credentials, loopback port):

```sh
docker run -d --name bank-crm-test-postgres -p 127.0.0.1:55433:5432 \
  -e POSTGRES_PASSWORD=crmtest -e POSTGRES_DB=crm_test postgres:16-alpine
uv run pytest
```

Tests use `TEST_DATABASE_URL`, defaulting to
`postgresql+asyncpg://postgres:crmtest@localhost:55433/crm_test`. They reject database
names without the `_test` suffix and never use the application's `DATABASE_URL`.
This must be a dedicated disposable instance: schema tests may recreate its tables.
Stop it with `docker stop bank-crm-test-postgres`. Clocks and SMS delivery are injected
in authentication tests; tests never send real SMS messages.
If the named test container already exists, use `docker start bank-crm-test-postgres`
instead of creating it again.
