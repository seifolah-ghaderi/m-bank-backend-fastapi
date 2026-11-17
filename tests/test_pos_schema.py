from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core import dates
from app.models import PosDevice, PosTransaction, PosVisit


async def sample_device(api):
    async with api.database.sessions.begin() as session:
        device = PosDevice(
            device_number="POS-001",
            owner_name="Test Owner",
            address="Synthetic address",
            branch_id=api.branches[0].id,
            created_by=api.users["supervisor"].id,
        )
        session.add(device)
    return device


async def test_runtime_snapshot_guard_and_open_uniqueness(api):
    device = await sample_device(api)
    values = dict(
        pos_device_id=device.id,
        branch_id=device.branch_id,
        selected_by=api.users["supervisor"].id,
        selected_at=dates.now(),
        snapshot_from_date=dates.today(),
        snapshot_to_date=dates.today(),
        snapshot_amount=None,
        snapshot_count=None,
        snapshot_no_data=True,
        snapshot_performance=None,
        snapshot_lower_threshold=Decimal(200000000),
        snapshot_upper_threshold=Decimal(1000000000),
        snapshot_policy_version=1,
    )
    async with api.database.sessions.begin() as session:
        await session.execute(text("SET LOCAL ROLE crm_runtime"))
        visit = PosVisit(**values)
        session.add(visit)
    with pytest.raises(DBAPIError):
        async with api.database.sessions.begin() as session:
            await session.execute(text("SET LOCAL ROLE crm_runtime"))
            await session.execute(
                text("UPDATE pos_visits SET snapshot_no_data=false WHERE id=:id"), {"id": visit.id}
            )
    with pytest.raises(IntegrityError):
        async with api.database.sessions.begin() as session:
            session.add(PosVisit(**values))
            await session.flush()
    async with api.database.sessions() as session:
        stored = await session.get(PosVisit, visit.id)
        assert stored.snapshot_no_data and stored.snapshot_amount is None


async def test_period_exclusion_and_negative_values(api):
    device = await sample_device(api)
    values = dict(
        pos_device_id=device.id,
        from_date=dates.today() - timedelta(days=5),
        to_date=dates.today(),
        transaction_amount=Decimal("100.01"),
        transaction_count=3,
    )
    async with api.database.sessions.begin() as session:
        session.add(PosTransaction(**values))
    with pytest.raises(IntegrityError):
        async with api.database.sessions.begin() as session:
            session.add(PosTransaction(**(values | {"from_date": dates.today()})))
            await session.flush()
    with pytest.raises(IntegrityError):
        async with api.database.sessions.begin() as session:
            session.add(PosTransaction(**(values | {"transaction_amount": Decimal(-1)})))
            await session.flush()
    async with api.database.sessions() as session:
        assert len((await session.scalars(select(PosTransaction))).all()) == 1
