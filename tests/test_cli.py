from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.cli import create_supervisor, purge_tokens
from app.core.errors import DomainError
from app.models import AuditLog, LoginChallenge, RefreshToken
from app.schemas.users import UserCreate


async def test_bootstrap_and_force(schema):
    details = UserCreate(
        first_name="Ali", last_name="Test", mobile="09123456789", role="supervisor"
    )
    first = await create_supervisor(schema, details, "ValidPass123")
    with pytest.raises(DomainError, match="supervisor_exists"):
        await create_supervisor(schema, details, "ValidPass123")
    second = await create_supervisor(
        schema, details.model_copy(update={"mobile": "09123456788"}), "ValidPass123", force=True
    )
    assert second != first
    async with schema.sessions() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(AuditLog).where(AuditLog.action == "bootstrap")
            )
            == 2
        )


async def test_purge_retains_live_records(api):
    now = api.clock.value
    user_id = api.users["supervisor"].id
    async with api.database.sessions.begin() as session:
        session.add_all(
            [
                RefreshToken(
                    user_id=user_id, token_hash="a" * 64, expires_at=now + timedelta(days=1)
                ),
                RefreshToken(
                    user_id=user_id, token_hash="b" * 64, expires_at=now - timedelta(days=31)
                ),
                RefreshToken(
                    user_id=user_id, token_hash="c" * 64, expires_at=now - timedelta(days=1)
                ),
                LoginChallenge(
                    user_id=user_id,
                    mobile="09123456780",
                    code_digest="d" * 64,
                    created_at=now - timedelta(days=40),
                    last_sent_at=now - timedelta(days=40),
                    expires_at=now - timedelta(days=40),
                    invalidated_at=now - timedelta(days=40),
                ),
            ]
        )
    assert await purge_tokens(api.database) == (1, 1)
    async with api.database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(RefreshToken)) == 2
