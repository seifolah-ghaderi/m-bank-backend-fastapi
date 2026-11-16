from sqlalchemy import func, select

from app.core import dates
from app.core.audit import record, snapshot
from app.core.deps import scope_for
from app.core.errors import DomainError
from app.core.pagination import paginate
from app.core.text import search_key
from app.core.validation import validated_changes
from app.models import Branch, City, User
from app.schemas.org import BranchOut, CityOut


async def get_entity(session, model, entity_id, user, *, lock=False):
    statement = select(model).where(model.id == entity_id, model.deleted_at.is_(None))
    if model is Branch:
        statement = scope_for(user).apply(statement, model)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    entity = await session.scalar(statement)
    if entity is None:
        raise DomainError(404, "not_found")
    return entity


async def branch_out(session, branch):
    city = await session.get(City, branch.city_id)
    manager = await session.scalar(
        select(User).where(
            User.branch_id == branch.id, User.role == "branch_manager", User.deleted_at.is_(None)
        )
    )
    count = await session.scalar(
        select(func.count())
        .select_from(User)
        .where(
            User.branch_id == branch.id,
            User.role == "employee",
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    )
    values = {
        field: getattr(branch, field) for field in BranchOut.model_fields if hasattr(branch, field)
    }
    return BranchOut(
        **values,
        city={"id": city.id, "name": city.name},
        manager={
            "id": manager.id,
            "full_name": f"{manager.first_name} {manager.last_name}",
            "mobile": manager.mobile,
        }
        if manager
        else None,
        active_employee_count=count,
    )


async def list_entities(
    session,
    model,
    user,
    params,
    q=None,
    include_inactive=None,
    is_active=None,
    branch_id=None,
    city_id=None,
):
    statement = select(model).where(model.deleted_at.is_(None))
    if model is Branch:
        statement = scope_for(user).apply(statement, model)
        if branch_id:
            if user.role != "supervisor" and branch_id != user.branch_id:
                raise DomainError(403, "forbidden")
            statement = statement.where(Branch.id == branch_id)
        if city_id:
            statement = statement.where(Branch.city_id == city_id)
    if q:
        statement = statement.where(func.lower(model.name).contains(search_key(q), autoescape=True))
    include = user.role == "supervisor" if include_inactive is None else include_inactive
    if is_active is not None:
        statement = statement.where(model.is_active == is_active)
    elif not include:
        statement = statement.where(model.is_active.is_(True))
    page = await paginate(
        session,
        statement,
        params,
        {"name": model.name, "created_at": model.created_at},
        "name",
        model.id,
    )
    page["items"] = [
        CityOut.model_validate(row) if model is City else await branch_out(session, row)
        for row in page["items"]
    ]
    return page


async def create_entity(session, model, body, actor, request):
    values = body.model_dump()
    if model is Branch:
        await get_entity(session, City, values["city_id"], actor, lock=True)
    entity = model(**values, created_by=actor.id, updated_by=actor.id)
    session.add(entity)
    await session.flush()
    record(
        session,
        actor,
        "create",
        model.__tablename__,
        entity.id,
        after=snapshot(entity),
        request=request,
    )
    return CityOut.model_validate(entity) if model is City else await branch_out(session, entity)


async def update_entity(session, model, entity_id, body, actor, request):
    required = {"name", "is_active"} | ({"city_id", "code"} if model is Branch else set())
    changes = validated_changes(body, required)
    if model is Branch and "city_id" in changes:
        await get_entity(session, City, changes["city_id"], actor, lock=True)
    entity = await get_entity(session, model, entity_id, actor, lock=True)
    before = snapshot(entity)
    for key, value in changes.items():
        setattr(entity, key, value)
    entity.updated_by = actor.id
    await session.flush()
    record(
        session, actor, "update", model.__tablename__, entity.id, before, snapshot(entity), request
    )
    return CityOut.model_validate(entity) if model is City else await branch_out(session, entity)


async def delete_entity(session, model, entity_id, actor, request):
    entity = await get_entity(session, model, entity_id, actor, lock=True)
    dependent, field = (Branch, Branch.city_id) if model is City else (User, User.branch_id)
    if await session.scalar(
        select(func.count())
        .select_from(dependent)
        .where(field == entity.id, dependent.deleted_at.is_(None))
    ):
        raise DomainError(409, "city_has_branches" if model is City else "branch_in_use")
    before = snapshot(entity)
    entity.deleted_at, entity.deleted_by, entity.updated_by = dates.now(), actor.id, actor.id
    await session.flush()
    record(
        session, actor, "delete", model.__tablename__, entity.id, before, snapshot(entity), request
    )
