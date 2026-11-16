import pytest
from sqlalchemy import func, select

from app.core.audit import present, record
from app.core.db import transaction
from app.core.errors import DomainError, Rejected, finish
from app.models import AuditLog, City


async def test_rollback_and_committed_security_rejection(schema):
    with pytest.raises(DomainError):
        async with transaction(schema) as session:
            city = City(name="Rollback")
            session.add(city)
            record(session, None, "create", "cities")
            await session.flush()
            raise DomainError(409, "conflict")
    async with schema.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(City)) == 0
        assert await session.scalar(select(func.count()).select_from(AuditLog)) == 0
    with pytest.raises(DomainError, match="invalid_credentials"):
        async with transaction(schema) as session:
            record(session, None, "login_failed", "users", after={"mobile": "0912***6789"})
            finish(Rejected(DomainError(401, "invalid_credentials")))
    async with schema.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(AuditLog)) == 1


async def test_audit_sanitization_and_atomic_success(schema, clock):
    async with transaction(schema) as session:
        city = City(name="Audited")
        session.add(city)
        await session.flush()
        record(
            session,
            None,
            "update",
            "cities",
            city.id,
            before={"name": "Old", "same": 1},
            after={
                "name": "New",
                "same": 1,
                "password_hash": "secret",
                "code": "123",
                "nested": {"refresh_token": "secret"},
                "when": clock.value,
            },
        )
    async with schema.sessions() as session:
        entry = await session.scalar(select(AuditLog))
        assert "same" not in entry.after
        assert "password_hash" not in entry.after
        assert "code" not in entry.after
        assert entry.after["nested"] == {}
        assert present(entry.after)["when"] == "1405/08/25T09:30:00+03:30"
        assert await session.scalar(select(City.name)) == "Audited"
