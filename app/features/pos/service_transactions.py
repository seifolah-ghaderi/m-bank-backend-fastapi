from sqlalchemy import select

from app.core import dates
from app.core.audit import record, snapshot
from app.core.deps import eligible, require_roles
from app.core.errors import DomainError
from app.core.lifecycle import lock_user
from app.core.pagination import paginate
from app.core.validation import input_values, validated_changes
from app.features.pos.service_devices import get_device
from app.models import PosTransaction
from app.schemas.pos import PosTransactionCreate, PosTransactionOut


async def transaction_actor(session, actor):
    actor = await lock_user(session, actor.id)
    eligible(actor)
    if actor.must_change_password:
        raise DomainError(403, "password_change_required")
    require_roles(actor, "supervisor")
    return actor


async def write_transaction(
    session, actor, device_id, body, request=None, *, import_id=None, upsert=False
):
    actor = await transaction_actor(session, actor)
    await get_device(session, device_id, actor, lock=True)
    overlap = await session.scalar(
        select(PosTransaction).where(
            PosTransaction.pos_device_id == device_id,
            PosTransaction.deleted_at.is_(None),
            PosTransaction.from_date <= body.to_date,
            PosTransaction.to_date >= body.from_date,
        )
    )
    if overlap:
        if not upsert or overlap.from_date != body.from_date or overlap.to_date != body.to_date:
            raise DomainError(
                409,
                "overlapping_period",
                details={
                    "from_date": dates.format_date(overlap.from_date),
                    "to_date": dates.format_date(overlap.to_date),
                },
            )
        if (
            overlap.transaction_amount == body.transaction_amount
            and overlap.transaction_count == body.transaction_count
        ):
            return overlap, "unchanged"
        before = snapshot(overlap)
        overlap.transaction_amount, overlap.transaction_count = (
            body.transaction_amount,
            body.transaction_count,
        )
        overlap.updated_by, overlap.import_id = actor.id, import_id
        await session.flush()
        record(
            session,
            actor,
            "update",
            "pos_monthly_transactions",
            overlap.id,
            before,
            snapshot(overlap),
            request,
        )
        return overlap, "updated"
    row = PosTransaction(
        pos_device_id=device_id,
        **input_values(body),
        source="import" if import_id else "manual",
        import_id=import_id,
        created_by=actor.id,
        updated_by=actor.id,
    )
    session.add(row)
    await session.flush()
    record(
        session,
        actor,
        "create",
        "pos_monthly_transactions",
        row.id,
        after=snapshot(row),
        request=request,
    )
    return row, "created"


async def transaction_history(session, actor, device_id, params, from_date=None, to_date=None):
    await get_device(session, device_id, actor)
    statement = select(PosTransaction).where(
        PosTransaction.pos_device_id == device_id, PosTransaction.deleted_at.is_(None)
    )
    if from_date is not None:
        statement = statement.where(PosTransaction.from_date >= from_date)
    if to_date is not None:
        statement = statement.where(PosTransaction.to_date <= to_date)
    page = await paginate(
        session,
        statement,
        params,
        {
            "from_date": PosTransaction.from_date,
            "to_date": PosTransaction.to_date,
            "transaction_amount": PosTransaction.transaction_amount,
        },
        "-from_date",
        PosTransaction.id,
    )
    page["items"] = [PosTransactionOut.model_validate(row) for row in page["items"]]
    return page


async def update_transaction(
    session, actor, transaction_id, body=None, request=None, *, delete=False
):
    actor = await transaction_actor(session, actor)
    row = await session.get(PosTransaction, transaction_id)
    if row is None or row.deleted_at is not None:
        raise DomainError(404, "not_found")
    await get_device(session, row.pos_device_id, actor, lock=True)
    await session.refresh(row, with_for_update=True)
    if row.deleted_at is not None:
        raise DomainError(404, "not_found")
    before = snapshot(row)
    if delete:
        row.deleted_at, row.deleted_by = dates.now(), actor.id
    else:
        changes = validated_changes(
            body, {"from_date", "to_date", "transaction_amount", "transaction_count"}
        )
        values = {key: getattr(row, key) for key in PosTransactionCreate.model_fields} | changes
        if (
            values["to_date"] < values["from_date"]
            or (values["to_date"] - values["from_date"]).days > 365
        ):
            raise DomainError(422, "invalid_period")
        conflict = await session.scalar(
            select(PosTransaction).where(
                PosTransaction.id != row.id,
                PosTransaction.pos_device_id == row.pos_device_id,
                PosTransaction.deleted_at.is_(None),
                PosTransaction.from_date <= values["to_date"],
                PosTransaction.to_date >= values["from_date"],
            )
        )
        if conflict:
            raise DomainError(
                409,
                "overlapping_period",
                details={
                    "from_date": dates.format_date(conflict.from_date),
                    "to_date": dates.format_date(conflict.to_date),
                },
            )
        for key, value in changes.items():
            setattr(row, key, value)
    row.updated_by = actor.id
    await session.flush()
    record(
        session,
        actor,
        "delete" if delete else "update",
        "pos_monthly_transactions",
        row.id,
        before,
        snapshot(row),
        request,
    )
    return row
