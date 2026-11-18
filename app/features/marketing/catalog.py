from sqlalchemy import select

from app.core.audit import record, snapshot
from app.core.errors import DomainError
from app.core.pagination import paginate
from app.core.text import search_key
from app.core.validation import input_values, validated_changes
from app.models import Occupation


async def list_entries(session, model, user, params, include_inactive):
    statement = select(model)
    if user.role != "supervisor" or not include_inactive:
        statement = statement.where(model.is_active)
    return await paginate(
        session,
        statement,
        params,
        {"name": model.name, "created_at": model.created_at},
        "name",
        model.id,
    )


async def save(session, model, body, user, request, entry_id=None):
    if entry_id is None:
        before = None
        values = input_values(body)
        entry = model(created_by=user.id)
        session.add(entry)
    else:
        entry = await session.scalar(select(model).where(model.id == entry_id).with_for_update())
        if entry is None:
            raise DomainError(404, "not_found")
        before = snapshot(entry)
        values = validated_changes(body, type(body).model_fields)
    for key, value in values.items():
        setattr(entry, key, value)
    if model is Occupation and "name" in values:
        entry.name_key = search_key(entry.name)
    entry.updated_by = user.id
    await session.flush()
    record(
        session,
        user,
        "create" if before is None else "update",
        model.__tablename__,
        entry.id,
        before,
        snapshot(entry),
        request,
    )
    return entry
