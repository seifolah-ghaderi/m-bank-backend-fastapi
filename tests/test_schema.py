from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.models import Branch, City, LoginChallenge, User


async def test_migration_tables_and_actor_fks(schema):
    async with schema.engine.connect() as connection:
        tables = await connection.run_sync(lambda c: inspect(c).get_table_names())
        assert set(tables) == {
            "alembic_version",
            "cities",
            "branches",
            "users",
            "refresh_tokens",
            "login_challenges",
            "audit_logs",
            "pos_devices",
            "pos_device_branch_history",
            "pos_device_owner_history",
            "pos_monthly_transactions",
            "pos_visits",
            "pos_visit_tag_links",
            "pos_tags",
            "pos_performance_settings",
            "notifications",
            "import_logs",
            "import_row_errors",
            "crm_imports",
            "crm_import_rows",
            "occupations",
            "banking_products",
            "leads",
            "campaigns",
            "campaign_leads",
            "campaign_quota_overrides",
            "visits",
            "visit_attempts",
            "customer_drafts",
            "customers",
            "product_sales",
            "sale_submissions",
            "sale_decisions",
            "customer_products",
            "retention_schedules",
            "retention_tasks",
            "score_transactions",
        }
        for name in ("cities", "branches", "users"):
            keys = await connection.run_sync(
                lambda c, table=name: inspect(c).get_foreign_keys(table)
            )
            assert {"created_by", "updated_by", "deleted_by"}.issubset(
                {k["constrained_columns"][0] for k in keys}
            )


async def test_unique_manager_and_pending_challenge(schema):
    async with schema.sessions.begin() as session:
        city = City(name="Tehran")
        session.add(city)
        await session.flush()
        branch = Branch(name="Main", code="TEH-01", city_id=city.id)
        session.add(branch)
        await session.flush()
        manager = User(
            first_name="Ali",
            last_name="Test",
            mobile="09123456789",
            password_hash="test",
            role="branch_manager",
            branch_id=branch.id,
            is_active=False,
        )
        session.add(manager)
        await session.flush()
        user_id, branch_id = manager.id, branch.id
    with pytest.raises(IntegrityError):
        async with schema.sessions.begin() as session:
            session.add(
                User(
                    first_name="Sara",
                    last_name="Test",
                    mobile="09123456788",
                    password_hash="test",
                    role="branch_manager",
                    branch_id=branch_id,
                )
            )
    now = datetime.now(UTC)
    with pytest.raises(IntegrityError):
        async with schema.sessions.begin() as session:
            for _ in range(2):
                session.add(
                    LoginChallenge(
                        user_id=user_id,
                        mobile="09123456789",
                        code_digest="0" * 64,
                        created_at=now,
                        last_sent_at=now,
                        expires_at=now + timedelta(minutes=5),
                    )
                )


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM cities",
        "DELETE FROM branches",
        "DELETE FROM users",
        "UPDATE audit_logs SET action='tampered'",
        "DELETE FROM audit_logs",
        "TRUNCATE audit_logs",
        "CREATE TABLE unauthorized(id int)",
        "DELETE FROM pos_devices",
        "DELETE FROM pos_visits",
        "DELETE FROM pos_device_branch_history",
        "DELETE FROM pos_device_owner_history",
        "DELETE FROM pos_monthly_transactions",
        "DELETE FROM pos_visit_tag_links",
        "DELETE FROM crm_imports",
        "UPDATE crm_import_rows SET outcome='failed'",
        "DELETE FROM crm_import_rows",
        "DELETE FROM leads",
        "DELETE FROM campaigns",
        "UPDATE visit_attempts SET result='pending'",
        "DELETE FROM visit_attempts",
        "UPDATE sale_submissions SET proof_text='tampered'",
        "UPDATE sale_decisions SET reason='tampered'",
        "UPDATE score_transactions SET points=0",
        "TRUNCATE score_transactions",
    ],
)
async def test_runtime_forbidden_privileges(schema, sql):
    with pytest.raises(DBAPIError):
        async with schema.sessions.begin() as session:
            await session.execute(text("SET LOCAL ROLE crm_runtime"))
            await session.execute(text(sql))


async def test_runtime_permitted_privileges(schema):
    async with schema.sessions.begin() as session:
        await session.execute(text("SET LOCAL ROLE crm_runtime"))
        city = City(name="Tehran")
        session.add(city)
        await session.flush()
        city.name = "Shiraz"
        await session.flush()
        await session.execute(
            text("INSERT INTO audit_logs(action,entity_type) VALUES ('create','cities')")
        )
        await session.execute(text("DELETE FROM refresh_tokens"))
        await session.execute(text("DELETE FROM login_challenges"))
        assert await session.scalar(select(City.name)) == "Shiraz"
