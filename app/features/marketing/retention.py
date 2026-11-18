from datetime import date, timedelta

from sqlalchemy import select

from app.core import dates
from app.core.audit import record, snapshot
from app.core.errors import DomainError
from app.core.pagination import paginate
from app.core.validation import input_values, validated_changes
from app.models import RetentionSchedule, RetentionTask


async def list_schedules(session, page, include_inactive):
    statement = select(RetentionSchedule)
    if not include_inactive:
        statement = statement.where(RetentionSchedule.is_active)
    return await paginate(
        session,
        statement,
        page,
        {
            "days_after_conversion": RetentionSchedule.days_after_conversion,
            "label": RetentionSchedule.label,
        },
        "days_after_conversion",
        RetentionSchedule.id,
    )


async def save_schedule(session, actor, request, body, schedule_id=None):
    if schedule_id is None:
        before = None
        row = RetentionSchedule(**input_values(body), created_by=actor.id)
        session.add(row)
    else:
        row = await session.scalar(
            select(RetentionSchedule).where(RetentionSchedule.id == schedule_id).with_for_update()
        )
        if row is None:
            raise DomainError(404, "not_found")
        before = snapshot(row)
        for key, value in validated_changes(body, type(body).model_fields).items():
            setattr(row, key, value)
    if row.days_after_conversion > (date.max - dates.today()).days:
        raise DomainError(422, "invalid_schedule_offset")
    row.updated_by = actor.id
    await session.flush()
    record(
        session,
        actor,
        "create" if before is None else "update",
        "retention_schedules",
        row.id,
        before,
        snapshot(row),
        request,
    )
    return row


async def generate_tasks(session, customer, actor):
    schedules = await session.scalars(select(RetentionSchedule).where(RetentionSchedule.is_active))
    for schedule in schedules:
        session.add(
            RetentionTask(
                customer_id=customer.id,
                retention_schedule_id=schedule.id,
                assigned_to=customer.acquired_by,
                due_date=customer.customer_since + timedelta(days=schedule.days_after_conversion),
                status="pending_approval" if schedule.requires_approval else "open",
                created_by=actor.id,
                updated_by=actor.id,
            )
        )
