from sqlalchemy import func, select, update

from app.core import dates
from app.core.errors import DomainError
from app.core.pagination import paginate
from app.models import Notification
from app.schemas.notifications import NotificationOut


async def notifications(session, actor, params, is_read=None):
    statement = select(Notification).where(Notification.recipient_id == actor.id)
    if is_read is not None:
        statement = statement.where(Notification.is_read == is_read)
    page = await paginate(
        session,
        statement,
        params,
        {"created_at": Notification.created_at},
        "-created_at",
        Notification.id,
    )
    page["items"] = [NotificationOut.model_validate(n) for n in page["items"]]
    return page


async def unread_count(session, actor):
    return {
        "count": await session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.recipient_id == actor.id, Notification.is_read.is_(False))
        )
    }


async def get_notification(session, actor, notification_id):
    row = await session.scalar(
        select(Notification).where(
            Notification.id == notification_id, Notification.recipient_id == actor.id
        )
    )
    if row is None:
        raise DomainError(404, "not_found")
    return row


async def mark_read(session, actor, notification_id=None):
    if notification_id is not None:
        await get_notification(session, actor, notification_id)
    statement = update(Notification).where(
        Notification.recipient_id == actor.id, Notification.is_read.is_(False)
    )
    if notification_id is not None:
        statement = statement.where(Notification.id == notification_id)
    await session.execute(statement.values(is_read=True, read_at=dates.now()))
    await session.flush()
