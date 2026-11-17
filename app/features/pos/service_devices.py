from datetime import timedelta

from sqlalchemy import func, or_, select

from app.core import dates
from app.core.audit import record, snapshot
from app.core.deps import require_roles, scope_for
from app.core.errors import DomainError
from app.core.lifecycle import active_branch, lifecycle_actor
from app.core.pagination import paginate
from app.core.text import search_key
from app.core.validation import validated_changes
from app.models import (
    Branch,
    City,
    PosBranchHistory,
    PosDevice,
    PosOwnerHistory,
    PosTransaction,
    PosVisit,
)
from app.models.pos import OPEN_STATES, OWNER_FIELDS
from app.schemas.pos import PosBranchHistoryOut, PosDeviceOut, PosOwnerHistoryOut


def device_query(
    actor,
    *,
    include_deleted=False,
    branch_id=None,
    city_id=None,
    status=None,
    source=None,
    q=None,
    has_open_visit=None,
    no_transactions_since=None,
):
    require_roles(actor, "supervisor", "branch_manager")
    statement = scope_for(actor).apply(select(PosDevice), PosDevice)
    if include_deleted:
        require_roles(actor, "supervisor")
    else:
        statement = statement.where(PosDevice.deleted_at.is_(None))
    if branch_id is not None:
        if actor.role != "supervisor" and branch_id != actor.branch_id:
            raise DomainError(403, "forbidden")
        statement = statement.where(PosDevice.branch_id == branch_id)
    if city_id is not None:
        statement = statement.where(
            PosDevice.branch_id.in_(select(Branch.id).where(Branch.city_id == city_id))
        )
    if status is not None:
        statement = statement.where(PosDevice.status == status)
    if source is not None:
        statement = statement.where(PosDevice.source == source)
    if q:
        statement = statement.where(
            or_(
                *[
                    func.lower(c).contains(search_key(q), autoescape=True)
                    for c in (
                        PosDevice.device_number,
                        PosDevice.owner_name,
                        PosDevice.shop_name,
                        PosDevice.address,
                    )
                ]
            )
        )
    if has_open_visit is not None:
        exists = (
            select(PosVisit.id)
            .where(PosVisit.pos_device_id == PosDevice.id, PosVisit.status.in_(OPEN_STATES))
            .exists()
        )
        statement = statement.where(exists if has_open_visit else ~exists)
    if no_transactions_since is not None:
        statement = statement.where(
            ~select(PosTransaction.id)
            .where(
                PosTransaction.pos_device_id == PosDevice.id,
                PosTransaction.deleted_at.is_(None),
                PosTransaction.to_date >= no_transactions_since,
            )
            .exists()
        )
    return statement


async def get_device(session, device_id, actor, *, lock=False, include_deleted=False):
    statement = device_query(actor, include_deleted=include_deleted).where(
        PosDevice.id == device_id
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    device = await session.scalar(statement)
    if device is None:
        raise DomainError(404, "not_found")
    return device


async def list_devices(session, actor, params, **filters):
    page = await paginate(
        session,
        device_query(actor, **filters),
        params,
        {
            "device_number": PosDevice.device_number,
            "owner_name": PosDevice.owner_name,
            "created_at": PosDevice.created_at,
            "status": PosDevice.status,
        },
        "device_number",
        PosDevice.id,
    )
    page["items"] = [PosDeviceOut.model_validate(d) for d in page["items"]]
    return page


async def export_devices(session, actor, **filters):
    from app.core.excel import workbook_bytes

    statement = device_query(actor, **filters)
    total = await session.scalar(select(func.count()).select_from(statement.subquery()))
    if total > 50000:
        raise DomainError(422, "too_many_rows")
    query = (
        statement.add_columns(Branch.code, Branch.name, City.name.label("city_name"))
        .join(Branch, Branch.id == PosDevice.branch_id)
        .join(City, City.id == Branch.city_id)
        .order_by(PosDevice.device_number, PosDevice.id)
    )
    rows = (await session.execute(query)).all()
    headers = [
        "device_number",
        "branch_code",
        "owner_name",
        "owner_mobile",
        "owner_national_code",
        "shop_name",
        "account_number",
        "contact_phone",
        "address",
        "status",
        "branch_name",
        "city",
    ]
    return workbook_bytes(
        headers,
        (
            [
                d.device_number,
                code,
                d.owner_name,
                d.owner_mobile,
                d.owner_national_code,
                d.shop_name,
                d.account_number,
                d.contact_phone,
                d.address,
                d.status,
                name,
                city,
            ]
            for d, code, name, city in rows
        ),
    )


async def detail(session, actor, device_id, *, include_deleted=False):
    from app.core.presentation import visit_out
    from app.schemas.pos import PosDeviceDetail

    device = await get_device(session, device_id, actor, include_deleted=include_deleted)
    branch = await session.get(Branch, device.branch_id)
    city = await session.get(City, branch.city_id)
    open_visit = await session.scalar(
        select(PosVisit).where(
            PosVisit.pos_device_id == device.id, PosVisit.status.in_(OPEN_STATES)
        )
    )
    completed = await session.scalar(
        select(PosVisit)
        .where(PosVisit.pos_device_id == device.id, PosVisit.status == "completed")
        .order_by(PosVisit.completed_at.desc(), PosVisit.id.desc())
        .limit(1)
    )
    last = await session.scalar(
        select(func.max(PosTransaction.to_date)).where(
            PosTransaction.pos_device_id == device.id, PosTransaction.deleted_at.is_(None)
        )
    )
    return PosDeviceDetail(
        **PosDeviceOut.model_validate(device).model_dump(),
        branch={
            "id": branch.id,
            "code": branch.code,
            "name": branch.name,
            "city": {"id": city.id, "name": city.name},
        },
        open_visit=(await visit_out(session, open_visit)).model_dump(mode="json")
        if open_visit
        else None,
        latest_completed_visit=(await visit_out(session, completed)).model_dump(mode="json")
        if completed
        else None,
        last_transaction_period_end=last,
    )


def effective(value, current=None):
    value = value or dates.today()
    if value > dates.today() or (current is not None and value < current):
        raise DomainError(422, "invalid_effective_date")
    return value


async def create_device(session, actor, body, request=None, *, source="manual", import_id=None):
    actor = await lifecycle_actor(session, actor, "supervisor")
    values = body.model_dump(exclude={"effective_date"})
    await active_branch(session, values["branch_id"])
    if await session.scalar(
        select(PosDevice.id).where(
            PosDevice.device_number == values["device_number"], PosDevice.deleted_at.is_(None)
        )
    ):
        raise DomainError(409, "device_number_in_use")
    start = effective(body.effective_date)
    device = PosDevice(
        **values, source=source, last_import_id=import_id, created_by=actor.id, updated_by=actor.id
    )
    session.add(device)
    await session.flush()
    session.add(
        PosBranchHistory(
            pos_device_id=device.id,
            branch_id=device.branch_id,
            from_date=start,
            created_by=actor.id,
            updated_by=actor.id,
        )
    )
    session.add(
        PosOwnerHistory(
            pos_device_id=device.id,
            from_date=start,
            **{k: getattr(device, k) for k in OWNER_FIELDS},
            created_by=actor.id,
            updated_by=actor.id,
        )
    )
    await session.flush()
    record(
        session, actor, "create", "pos_devices", device.id, after=snapshot(device), request=request
    )
    return device


async def update_device(session, actor, device_id, body, request=None):
    actor = await lifecycle_actor(session, actor, "supervisor")
    device = await get_device(session, device_id, actor, lock=True)
    changes = validated_changes(body, {"device_number", "owner_name", "address", "status"})
    before = snapshot(device)
    for key, value in changes.items():
        setattr(device, key, value)
    device.updated_by = actor.id
    if set(changes) & set(OWNER_FIELDS):
        history = await session.scalar(
            select(PosOwnerHistory)
            .where(PosOwnerHistory.pos_device_id == device.id, PosOwnerHistory.to_date.is_(None))
            .with_for_update()
        )
        old = snapshot(history)
        for key in OWNER_FIELDS:
            setattr(history, key, getattr(device, key))
        history.updated_by = actor.id
        record(
            session,
            actor,
            "correct_owner",
            history.__tablename__,
            history.id,
            before=old,
            after=snapshot(history),
            request=request,
        )
    await session.flush()
    record(session, actor, "update", "pos_devices", device.id, before, snapshot(device), request)
    return device


async def change_history(session, model, device, actor, start, values, request):
    history = await session.scalar(
        select(model)
        .where(model.pos_device_id == device.id, model.to_date.is_(None))
        .with_for_update()
    )
    start = effective(start, history.from_date)
    before = snapshot(history)
    if start == history.from_date:
        for key, value in values.items():
            setattr(history, key, value)
        history.updated_by = actor.id
        record(
            session,
            actor,
            "correct_history",
            model.__tablename__,
            history.id,
            before,
            snapshot(history),
            request,
        )
    else:
        history.to_date, history.updated_by = start - timedelta(days=1), actor.id
        await session.flush()
        record(
            session,
            actor,
            "close_history",
            model.__tablename__,
            history.id,
            before,
            snapshot(history),
            request,
        )
        new = model(
            pos_device_id=device.id,
            from_date=start,
            **values,
            created_by=actor.id,
            updated_by=actor.id,
        )
        session.add(new)
        await session.flush()
        record(
            session,
            actor,
            "create_history",
            model.__tablename__,
            new.id,
            after=snapshot(new),
            request=request,
        )


async def transfer(session, actor, device_id, body, request=None):
    from app.core.notifications import cancel_device_work

    actor = await lifecycle_actor(session, actor, "supervisor")
    await active_branch(session, body.to_branch_id)
    device = await get_device(session, device_id, actor, lock=True)
    if device.branch_id == body.to_branch_id:
        raise DomainError(409, "same_branch")
    before = snapshot(device)
    await change_history(
        session,
        PosBranchHistory,
        device,
        actor,
        body.effective_date,
        {"branch_id": body.to_branch_id, "reason": body.reason},
        request,
    )
    await cancel_device_work(session, device, actor, "device_transferred", request)
    device.branch_id, device.updated_by = body.to_branch_id, actor.id
    await session.flush()
    record(session, actor, "transfer", "pos_devices", device.id, before, snapshot(device), request)
    return device


async def change_owner(session, actor, device_id, body, request=None):
    actor = await lifecycle_actor(session, actor, "supervisor")
    device = await get_device(session, device_id, actor, lock=True)
    before = snapshot(device)
    values = body.model_dump(exclude={"effective_date"})
    await change_history(
        session, PosOwnerHistory, device, actor, body.effective_date, values, request
    )
    for key, value in values.items():
        setattr(device, key, value)
    device.updated_by = actor.id
    await session.flush()
    record(
        session, actor, "change_owner", "pos_devices", device.id, before, snapshot(device), request
    )
    return device


async def delete_restore(session, actor, device_id, request=None, *, restore=False):
    actor = await lifecycle_actor(session, actor, "supervisor")
    device = await get_device(session, device_id, actor, lock=True, include_deleted=restore)
    before = snapshot(device)
    if restore:
        if await session.scalar(
            select(PosDevice.id).where(
                PosDevice.device_number == device.device_number,
                PosDevice.deleted_at.is_(None),
                PosDevice.id != device.id,
            )
        ):
            raise DomainError(409, "device_number_in_use")
        device.deleted_at = device.deleted_by = None
    else:
        if await session.scalar(
            select(PosVisit.id).where(
                PosVisit.pos_device_id == device.id, PosVisit.status.in_(OPEN_STATES)
            )
        ):
            raise DomainError(409, "device_has_open_visit")
        device.deleted_at, device.deleted_by = dates.now(), actor.id
    device.updated_by = actor.id
    await session.flush()
    record(
        session,
        actor,
        "restore" if restore else "delete",
        "pos_devices",
        device.id,
        before,
        snapshot(device),
        request,
    )
    return device


async def history(session, actor, device_id, kind, params):
    await get_device(session, device_id, actor)
    model, schema = (
        (PosBranchHistory, PosBranchHistoryOut)
        if kind == "branch"
        else (PosOwnerHistory, PosOwnerHistoryOut)
    )
    page = await paginate(
        session,
        select(model).where(model.pos_device_id == device_id),
        params,
        {"from_date": model.from_date},
        "-from_date",
        model.id,
    )
    page["items"] = [schema.model_validate(row) for row in page["items"]]
    return page
