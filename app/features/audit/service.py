from sqlalchemy import select

from app.core.audit import present
from app.core.dates import day_bound
from app.core.errors import DomainError
from app.core.pagination import paginate
from app.models import AuditLog
from app.schemas.audit import AuditOut


async def list_audit(
    session,
    params,
    entity_type=None,
    entity_id=None,
    actor_id=None,
    action=None,
    from_date=None,
    to_date=None,
):
    if from_date and to_date and from_date > to_date:
        raise DomainError(422, "invalid_date_range")
    statement = select(AuditLog)
    for field, value in (
        (AuditLog.entity_type, entity_type),
        (AuditLog.entity_id, entity_id),
        (AuditLog.actor_id, actor_id),
        (AuditLog.action, action),
    ):
        if value is not None:
            statement = statement.where(field == value)
    if from_date:
        statement = statement.where(AuditLog.occurred_at >= day_bound(from_date))
    if to_date:
        statement = statement.where(AuditLog.occurred_at < day_bound(to_date, after=True))
    page = await paginate(
        session,
        statement,
        params,
        {"occurred_at": AuditLog.occurred_at},
        "-occurred_at",
        AuditLog.id,
    )
    result = []
    for row in page["items"]:
        output = AuditOut.model_validate(row)
        output.before, output.after = present(row.before), present(row.after)
        result.append(output)
    page["items"] = result
    return page
