from datetime import date, timedelta

from sqlalchemy import select

from app.core import dates
from app.core.audit import record, snapshot
from app.core.deps import scope_for
from app.core.errors import DomainError
from app.core.lifecycle import lifecycle_actor
from app.core.pagination import paginate
from app.core.validation import input_values, validated_changes
from app.models import Customer, RetentionSchedule, RetentionTask


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
        row = RetentionSchedule(
            **input_values(body, exclude={"requires_approval"}), created_by=actor.id
        )
        session.add(row)
    else:
        row = await session.scalar(
            select(RetentionSchedule).where(RetentionSchedule.id == schedule_id).with_for_update()
        )
        if row is None:
            raise DomainError(404, "not_found")
        before = snapshot(row)
        changes = validated_changes(body, type(body).model_fields)
        changes.pop("requires_approval", None)
        for key, value in changes.items():
            setattr(row, key, value)
    if row.days_after_conversion > (date.max - dates.today()).days:
        raise DomainError(422, "invalid_schedule_offset")
    row.requires_approval = False
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
                status="open",
                created_by=actor.id,
                updated_by=actor.id,
            )
        )


def scoped_tasks(statement, user):
    statement = scope_for(user).apply(
        statement.join(Customer, Customer.id == RetentionTask.customer_id), Customer
    )
    if user.role == "employee":
        statement = statement.where(
            RetentionTask.assigned_to == user.id,
            RetentionTask.status.in_(("open", "completed")),
        )
    return statement


def task_summary(task, label):
    return {
        "id": task.id,
        "customer_id": task.customer_id,
        "schedule_id": task.retention_schedule_id,
        "label": label,
        "assigned_to": task.assigned_to,
        "due_date": task.due_date,
        "status": task.status,
        "visit_date": task.visit_date,
        "result": task.result,
        "completed_at": task.completed_at,
        "completed_by": task.completed_by,
    }


async def list_tasks(session, user, page, status):
    statement = scoped_tasks(select(RetentionTask), user)
    if status is None and user.role == "employee":
        status = "open"
    if status is not None:
        statement = statement.where(RetentionTask.status == status)
    result = await paginate(
        session, statement, page, {"due_date": RetentionTask.due_date}, "due_date", RetentionTask.id
    )
    tasks = result["items"]
    if tasks:
        rows = await session.execute(
            select(RetentionSchedule.id, RetentionSchedule.label).where(
                RetentionSchedule.id.in_({task.retention_schedule_id for task in tasks})
            )
        )
        labels = dict(rows.all())
        result["items"] = [task_summary(task, labels[task.retention_schedule_id]) for task in tasks]
    return result


async def get_task(session, user, task_id, *, lock=False):
    statement = (
        scoped_tasks(select(RetentionTask, RetentionSchedule.label, Customer), user)
        .join(RetentionSchedule, RetentionSchedule.id == RetentionTask.retention_schedule_id)
        .where(RetentionTask.id == task_id)
    )
    if lock:
        statement = statement.with_for_update(of=RetentionTask)
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        raise DomainError(404, "not_found")
    return row


async def task_detail(session, user, task_id):
    task, label, customer = await get_task(session, user, task_id)
    return task_summary(task, label) | {"customer": customer, "notes": task.notes}


async def complete_task(session, user, task_id, body, request):
    actor = await lifecycle_actor(session, user, "employee")
    task, label, customer = await get_task(session, actor, task_id, lock=True)
    if task.status != "open":
        raise DomainError(409, "retention_task_not_open")
    if body.visit_date > dates.today():
        raise DomainError(422, "invalid_visit_date")

    task.visit_date = body.visit_date
    task.result = body.result
    task.notes = body.notes
    task.status = "completed"
    task.completed_at = dates.now()
    task.completed_by = task.updated_by = actor.id
    record(
        session,
        actor,
        "complete",
        "retention_tasks",
        task.id,
        before={"status": "open"},
        after={
            "status": task.status,
            "visit_date": task.visit_date,
            "completed_at": task.completed_at,
            "completed_by": task.completed_by,
        },
        request=request,
    )
    await session.flush()
    return task_summary(task, label) | {"customer": customer, "notes": task.notes}
