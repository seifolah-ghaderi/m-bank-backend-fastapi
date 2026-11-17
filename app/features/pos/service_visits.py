from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core import dates
from app.core.audit import record, snapshot
from app.core.db import integrity_error
from app.core.deps import require_roles, scope_for
from app.core.errors import DomainError
from app.core.lifecycle import active_branch, lifecycle_actor, lock_user
from app.core.notifications import branch_manager_id, cancel_work, notify
from app.core.pagination import paginate
from app.core.presentation import visit_out
from app.core.validation import validated_changes
from app.features.pos.productivity import productivity_query
from app.models import Branch, PosDevice, PosTag, PosVisit, PosVisitTagLink
from app.models.pos import OPEN_STATES
from app.schemas.pos import PosDeviceOut, PosTagOut


def scoped_visits(actor):
    return scope_for(actor).apply(select(PosVisit), PosVisit)


async def get_visit(session, actor, visit_id):
    visit = await session.scalar(scoped_visits(actor).where(PosVisit.id == visit_id))
    if visit is None:
        raise DomainError(404, "not_found")
    return visit


async def locked_visit(session, actor, visit_id):
    visit = await get_visit(session, actor, visit_id)
    await session.execute(
        select(PosDevice.id).where(PosDevice.id == visit.pos_device_id).with_for_update()
    )
    return await session.scalar(
        scoped_visits(actor)
        .where(PosVisit.id == visit_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def dispatch(session, actor, body, request=None):
    actor = await lifecycle_actor(session, actor, "supervisor")
    start, end = dates.period_range(
        jalali_year=body.jalali_year,
        jalali_month=body.jalali_month,
        from_date=body.from_date,
        to_date=body.to_date,
    )
    await session.execute(
        select(PosDevice.id)
        .where(PosDevice.id.in_(body.pos_device_ids))
        .order_by(PosDevice.id)
        .with_for_update()
    )
    query = productivity_query(actor, start, end).subquery()
    snapshots = {
        r["pos_device_id"]: r
        for r in (
            await session.execute(
                select(query).where(query.c.pos_device_id.in_(body.pos_device_ids))
            )
        ).mappings()
    }
    results = []
    for device_id in body.pos_device_ids:
        try:
            async with session.begin_nested():
                values = snapshots.get(device_id)
                if values is None:
                    raise DomainError(404, "not_found")
                if values["status"] == "retired":
                    raise DomainError(409, "device_retired")
                branch = await session.get(Branch, values["branch_id"])
                if branch.deleted_at is not None or not branch.is_active:
                    raise DomainError(422, "branch_inactive")
                if await session.scalar(
                    select(PosVisit.id).where(
                        PosVisit.pos_device_id == device_id, PosVisit.status.in_(OPEN_STATES)
                    )
                ):
                    raise DomainError(409, "device_has_open_visit")
                visit = PosVisit(
                    pos_device_id=device_id,
                    branch_id=values["branch_id"],
                    selected_by=actor.id,
                    selected_at=dates.now(),
                    created_by=actor.id,
                    updated_by=actor.id,
                    instructions=body.instructions,
                    snapshot_from_date=start,
                    snapshot_to_date=end,
                    snapshot_amount=values["transaction_amount"],
                    snapshot_count=values["transaction_count"],
                    snapshot_no_data=values["no_data"],
                    snapshot_performance=values["performance"],
                    snapshot_lower_threshold=values["lower_threshold"],
                    snapshot_upper_threshold=values["upper_threshold"],
                    snapshot_policy_version=values["policy_version"],
                )
                session.add(visit)
                await session.flush()
                notify(
                    session,
                    await branch_manager_id(session, visit.branch_id),
                    "pos_visit_dispatched",
                    visit,
                )
                record(
                    session,
                    actor,
                    "dispatch",
                    "pos_visits",
                    visit.id,
                    after=snapshot(visit),
                    request=request,
                )
                result = {
                    "pos_device_id": str(device_id),
                    "status": "created",
                    "visit_id": str(visit.id),
                    "branch_id": str(visit.branch_id),
                }
            results.append(result)
        except (DomainError, IntegrityError) as error:
            if isinstance(error, IntegrityError):
                error = integrity_error(error)
            results.append(
                {"pos_device_id": str(device_id), "status": "error", "error_code": error.code}
            )
    return results


async def assign(session, actor, visit_id, body, request=None, *, reassign=False):
    actor = await lifecycle_actor(session, actor, "branch_manager")
    draft = await get_visit(session, actor, visit_id)
    assignee = await lock_user(session, body.assigned_to)
    if (
        not assignee
        or assignee.deleted_at is not None
        or not assignee.is_active
        or assignee.role != "employee"
        or assignee.branch_id != draft.branch_id
    ):
        raise DomainError(422, "invalid_assignee")
    await active_branch(session, draft.branch_id)
    visit = await locked_visit(session, actor, visit_id)
    expected = "assigned" if reassign else "pending_assignment"
    if visit.status not in OPEN_STATES:
        raise DomainError(409, "visit_archived")
    if visit.status != expected:
        raise DomainError(409, "visit_already_assigned" if not reassign else "visit_not_assigned")
    if body.due_date is not None and body.due_date < dates.today():
        raise DomainError(422, "invalid_due_date")
    before = snapshot(visit)
    previous = visit.assigned_to
    visit.assigned_to, visit.assigned_by, visit.assigned_at = assignee.id, actor.id, dates.now()
    if "due_date" in body.model_fields_set:
        visit.due_date = body.due_date
    if "instructions" in body.model_fields_set:
        visit.instructions = body.instructions
    visit.status, visit.updated_by = "assigned", actor.id
    await session.flush()
    if previous is not None and previous != assignee.id:
        notify(session, previous, "pos_visit_unassigned", visit)
    notify(session, assignee.id, "pos_visit_assigned", visit)
    record(
        session,
        actor,
        "reassign" if reassign else "assign",
        "pos_visits",
        visit.id,
        before,
        snapshot(visit),
        request,
    )
    return await visit_out(session, visit)


async def bulk_assign(session, actor, body, request=None):
    actor = await lifecycle_actor(session, actor, "branch_manager")
    results = []
    for visit_id in body.visit_ids:
        try:
            async with session.begin_nested():
                await assign(session, actor, visit_id, body, request)
            results.append({"visit_id": str(visit_id), "status": "assigned"})
        except (DomainError, IntegrityError) as error:
            if isinstance(error, IntegrityError):
                error = integrity_error(error)
            results.append({"visit_id": str(visit_id), "status": "error", "error_code": error.code})
    return results


async def cancel(session, actor, visit_id, reason, request=None):
    actor = await lifecycle_actor(session, actor, "supervisor", "branch_manager")
    visit = await locked_visit(session, actor, visit_id)
    if visit.status not in OPEN_STATES:
        raise DomainError(409, "visit_archived")
    if not reason.strip():
        raise DomainError(422, "invalid_cancel_reason")
    await cancel_work(session, visit, actor, reason, request)
    return await visit_out(session, visit)


async def set_tags(session, visit, codes):
    if len(set(codes)) != len(codes):
        raise DomainError(422, "invalid_tags")
    tags = list(
        await session.scalars(
            select(PosTag).where(PosTag.code.in_(codes), PosTag.is_active.is_(True))
        )
    )
    if len(tags) != len(codes):
        raise DomainError(422, "invalid_tags")
    desired = {tag.id for tag in tags}
    links = list(
        await session.scalars(
            select(PosVisitTagLink).where(PosVisitTagLink.pos_visit_id == visit.id)
        )
    )
    existing = {link.tag_id for link in links}
    for link in links:
        link.is_active = link.tag_id in desired
    for tag_id in desired - existing:
        session.add(PosVisitTagLink(pos_visit_id=visit.id, tag_id=tag_id))
    await session.flush()


async def complete(session, actor, visit_id, body, request=None, *, correction=False):
    actor = await lifecycle_actor(session, actor, "supervisor" if correction else "employee")
    visit = await locked_visit(session, actor, visit_id)
    if correction:
        if visit.status != "completed":
            raise DomainError(409, "visit_not_completed")
    elif visit.status != "assigned":
        raise DomainError(
            409, "visit_archived" if visit.status not in OPEN_STATES else "visit_not_assigned"
        )
    old = await visit_out(session, visit)
    before = snapshot(visit) | {"tag_codes": old.tag_codes}
    if not correction:
        visited = body.visited_at or dates.now()
        if visited > dates.now() or visited < visit.assigned_at:
            raise DomainError(422, "invalid_visit_time")
        visit.visited_at, visit.completed_at, visit.status = visited, dates.now(), "completed"
    visit.result, visit.description, visit.updated_by = body.result, body.description, actor.id
    await set_tags(session, visit, body.tag_codes)
    await session.flush()
    if not correction:
        notify(session, visit.assigned_by, "pos_visit_completed", visit)
    record(
        session,
        actor,
        "correct_visit" if correction else "complete",
        "pos_visits",
        visit.id,
        before,
        snapshot(visit) | {"tag_codes": body.tag_codes},
        request,
    )
    return await visit_out(session, visit)


async def detail(session, actor, visit_id):
    visit = await get_visit(session, actor, visit_id)
    result = (await visit_out(session, visit)).model_dump(mode="json")
    device = await session.get(PosDevice, visit.pos_device_id)
    result["device"] = PosDeviceOut.model_validate(device).model_dump(mode="json")
    branch = await session.get(Branch, visit.branch_id)
    result["branch"] = {"id": str(branch.id), "name": branch.name, "code": branch.code}
    previous = await session.scalar(
        select(PosVisit)
        .where(
            PosVisit.pos_device_id == visit.pos_device_id,
            PosVisit.status == "completed",
            PosVisit.id != visit.id,
        )
        .order_by(PosVisit.completed_at.desc(), PosVisit.id.desc())
        .limit(1)
    )
    result["latest_completed_visit_tags"] = (
        (await visit_out(session, previous)).tag_codes if previous else []
    )
    return result


async def list_visits(
    session,
    actor,
    params,
    *,
    status=None,
    archived=None,
    assigned_to=None,
    branch_id=None,
    pos_device_id=None,
    result=None,
    tag=None,
    overdue=None,
    assigned_from=None,
    assigned_to_date=None,
    completed_from=None,
    completed_to=None,
    due_from=None,
    due_to=None,
):
    statement = scoped_visits(actor)
    if status is None and actor.role == "employee" and archived is None:
        status = "assigned"
    if status is not None:
        statement = statement.where(PosVisit.status == status)
    if archived is not None:
        clause = PosVisit.status.in_(("completed", "cancelled"))
        statement = statement.where(clause if archived else ~clause)
    for value, column in (
        (assigned_to, PosVisit.assigned_to),
        (pos_device_id, PosVisit.pos_device_id),
        (result, PosVisit.result),
    ):
        if value is not None:
            statement = statement.where(column == value)
    if branch_id is not None:
        if actor.role != "supervisor" and actor.branch_id != branch_id:
            raise DomainError(403, "forbidden")
        statement = statement.where(PosVisit.branch_id == branch_id)
    if tag is not None:
        statement = statement.where(
            select(PosVisitTagLink.pos_visit_id)
            .join(PosTag, PosTag.id == PosVisitTagLink.tag_id)
            .where(
                PosVisitTagLink.pos_visit_id == PosVisit.id,
                PosTag.code == tag,
                PosVisitTagLink.is_active.is_(True),
            )
            .exists()
        )
    if overdue is not None:
        clause = (PosVisit.status == "assigned") & (PosVisit.due_date < dates.today())
        statement = statement.where(clause if overdue else (~clause | PosVisit.due_date.is_(None)))
    for value, column, after in (
        (assigned_from, PosVisit.assigned_at, False),
        (assigned_to_date, PosVisit.assigned_at, True),
        (completed_from, PosVisit.completed_at, False),
        (completed_to, PosVisit.completed_at, True),
    ):
        if value is not None:
            statement = statement.where(
                column < dates.day_bound(value, after=True)
                if after
                else column >= dates.day_bound(value)
            )
    if due_from:
        statement = statement.where(PosVisit.due_date >= due_from)
    if due_to:
        statement = statement.where(PosVisit.due_date <= due_to)
    page = await paginate(
        session,
        statement,
        params,
        {
            "selected_at": PosVisit.selected_at,
            "assigned_at": PosVisit.assigned_at,
            "due_date": PosVisit.due_date,
            "completed_at": PosVisit.completed_at,
        },
        "due_date" if actor.role == "employee" else "-selected_at",
        PosVisit.id,
    )
    page["items"] = [await visit_out(session, v) for v in page["items"]]
    return page


async def tags(session, actor, params, include_inactive=False):
    statement = select(PosTag)
    if include_inactive:
        require_roles(actor, "supervisor")
    else:
        statement = statement.where(PosTag.is_active.is_(True))
    page = await paginate(
        session, statement, params, {"name": PosTag.name, "code": PosTag.code}, "name", PosTag.id
    )
    page["items"] = [PosTagOut.model_validate(t) for t in page["items"]]
    return page


async def save_tag(session, actor, body, request=None, tag_id=None):
    actor = await lifecycle_actor(session, actor, "supervisor")
    if tag_id:
        tag = await session.get(PosTag, tag_id)
        if tag is None:
            raise DomainError(404, "not_found")
        before = snapshot(tag) | {"tag_code": tag.code}
        for key, value in validated_changes(body, {"name", "is_active"}).items():
            setattr(tag, key, value)
        tag.updated_by = actor.id
    else:
        tag = PosTag(**body.model_dump(), created_by=actor.id, updated_by=actor.id)
        session.add(tag)
        before = None
    await session.flush()
    record(
        session,
        actor,
        "update" if tag_id else "create",
        "pos_tags",
        tag.id,
        before,
        snapshot(tag) | {"tag_code": tag.code},
        request,
    )
    return PosTagOut.model_validate(tag)
