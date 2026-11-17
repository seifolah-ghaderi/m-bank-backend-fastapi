from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import inspect

from app.core.dates import format_date, format_datetime
from app.models import AuditLog

SECRET_FIELDS = {
    "password",
    "password_hash",
    "current_password",
    "new_password",
    "temporary_password",
    "code",
    "code_digest",
    "token",
    "token_hash",
    "access_token",
    "refresh_token",
    "sms_api_key",
    "jwt_secret",
    "csrf_secret",
    "sms_digest_secret",
    "csrf_token",
}


def sanitize(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return {"$datetime": value.isoformat()}
    if isinstance(value, date):
        return {"$date": value.isoformat()}
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {k: sanitize(v) for k, v in value.items() if k not in SECRET_FIELDS}
    if isinstance(value, (list, tuple)):
        return [sanitize(v) for v in value]
    return value


def present(value):
    """Convert only typed audit markers, never arbitrary text or identifiers."""
    if isinstance(value, dict):
        if set(value) == {"$datetime"}:
            return format_datetime(datetime.fromisoformat(value["$datetime"]))
        if set(value) == {"$date"}:
            return format_date(date.fromisoformat(value["$date"]))
        return {k: present(v) for k, v in value.items()}
    if isinstance(value, list):
        return [present(v) for v in value]
    return value


def snapshot(entity):
    return {
        column.key: getattr(entity, column.key)
        for column in inspect(type(entity)).columns
        if column.key not in SECRET_FIELDS
    }


def record(
    session, actor, action, entity_type, entity_id=None, before=None, after=None, request=None
):
    before, after = sanitize(before), sanitize(after)
    if before is not None and after is not None:
        changed = {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}
        before = {key: before[key] for key in changed if key in before}
        after = {key: after[key] for key in changed if key in after}
    row = AuditLog(
        actor_id=actor.id if actor else None,
        actor_role=actor.role if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
        request_id=UUID(request.state.request_id) if request else None,
        ip=request.client.host[:45] if request and request.client else None,
    )
    session.add(row)
    return row
