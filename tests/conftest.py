import os
import subprocess
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core import dates
from app.core.config import Settings
from app.core.db import Database
from app.core.security import access_token, hasher
from app.main import create_app
from app.models import Branch, City, PosPerformanceSettings, PosTag, User

MIGRATED_URLS = set()


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://test:test@localhost:55433/crm_test",
        jwt_secret="j" * 32,
        csrf_secret="c" * 32,
        sms_digest_secret="s" * 32,
        environment="dev",
        sms_mode="fixed",
        cors_origins=["http://localhost:5173"],
    )


@pytest.fixture
async def database():
    url = os.getenv(
        "TEST_DATABASE_URL", "postgresql+asyncpg://postgres:crmtest@localhost:55433/crm_test"
    )
    # Database tests must never silently fall back to DATABASE_URL or a production name.
    if not urlsplit(url).path.removeprefix("/").endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must name a disposable database ending in _test")
    database = Database(url)
    try:
        yield database
    finally:
        await database.close()


@pytest.fixture
def clock(monkeypatch):
    state = SimpleNamespace(value=datetime(2026, 11, 16, 6, tzinfo=UTC))

    def advance(**kwargs):
        state.value += timedelta(**kwargs)

    state.advance = advance
    monkeypatch.setattr(dates, "now", lambda: state.value)
    return state


@pytest.fixture
async def schema(database):
    async with database.engine.begin() as connection:
        await connection.execute(
            text("""DO $$ BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='crm_runtime') THEN
            CREATE ROLE crm_runtime LOGIN PASSWORD 'crmtest' NOSUPERUSER NOINHERIT;
          END IF;
        END $$""")
        )
    url = database.engine.url.render_as_string(hide_password=False)
    if url not in MIGRATED_URLS:
        result = subprocess.run(
            [".venv/bin/alembic", "upgrade", "head"],
            env=os.environ
            | {
                "MIGRATION_DATABASE_URL": url,
                "DATABASE_URL": url,
                "JWT_SECRET": "test-jwt" * 8,
                "CSRF_SECRET": "test-csrf" * 8,
                "SMS_DIGEST_SECRET": "test-sms" * 8,
                "ENVIRONMENT": "dev",
                "SMS_MODE": "fixed",
            },
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, "Disposable migration failed: " + result.stderr
        MIGRATED_URLS.add(url)
    async with database.engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE cities, branches, users, refresh_tokens, "
                "login_challenges, audit_logs RESTART IDENTITY CASCADE"
            )
        )
    async with database.sessions.begin() as session:
        session.add(
            PosPerformanceSettings(
                id=1, lower_threshold=200000000, upper_threshold=1000000000, policy_version=1
            )
        )
        session.add_all(
            [
                PosTag(code=code, name=name)
                for code, name in (
                    ("broken_device", "Broken Device"),
                    ("new_service_requested", "New Service Requested"),
                    ("maintenance_required", "Maintenance Required"),
                )
            ]
        )
    return database


@pytest.fixture
async def api(schema, settings, clock):
    encoded = hasher.hash("ValidPass123")
    async with schema.sessions.begin() as session:
        city = City(name="تهران")
        session.add(city)
        await session.flush()
        branches = [Branch(name=f"Branch {i}", code=f"TEH-{i}", city_id=city.id) for i in (1, 2)]
        session.add_all(branches)
        await session.flush()
        users = {}
        roles = [
            ("supervisor", None),
            ("supervisor2", None),
            ("manager", branches[0].id),
            ("employee", branches[0].id),
            ("other", branches[1].id),
        ]
        for i, (key, branch_id) in enumerate(roles):
            role = (
                "supervisor"
                if key.startswith("supervisor")
                else "branch_manager"
                if key == "manager"
                else "employee"
            )
            users[key] = User(
                first_name=f"Name{i}",
                last_name="Test",
                mobile=f"0912345678{i}",
                password_hash=encoded,
                role=role,
                branch_id=branch_id,
                must_change_password=False,
            )
        session.add_all(users.values())
    app = create_app(settings)
    await app.state.database.close()
    app.state.database = schema
    headers = {
        key: {"Authorization": "Bearer " + access_token(settings, user)}
        for key, user in users.items()
    }
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Origin": settings.cors_origins[0]},
    ) as client:
        yield SimpleNamespace(
            app=app,
            client=client,
            users=users,
            branches=branches,
            city=city,
            headers=headers,
            database=schema,
            clock=clock,
            settings=settings,
        )
