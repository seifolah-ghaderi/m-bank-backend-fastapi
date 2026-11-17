from sqlalchemy import select

from app.core import dates
from app.core.audit import record, snapshot
from app.models import Notification, PosVisit, User
from app.models.pos import OPEN_STATES


def notify(session, recipient_id, event_type, visit):
    if recipient_id is not None:
        session.add(
            Notification(
                recipient_id=recipient_id,
                event_type=event_type,
                title=event_type.replace("_", " ").capitalize(),
                payload={"visit_id": str(visit.id), "pos_device_id": str(visit.pos_device_id)},
            )
        )


async def branch_manager_id(session, branch_id):
    return await session.scalar(
        select(User.id).where(
            User.branch_id == branch_id,
            User.role == "branch_manager",
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    )


async def cancel_work(session, visit, actor, reason, request=None):
    before = snapshot(visit)
    recipient = visit.assigned_to or await branch_manager_id(session, visit.branch_id)
    visit.status, visit.cancel_reason = "cancelled", reason
    visit.cancelled_at, visit.cancelled_by, visit.updated_by = dates.now(), actor.id, actor.id
    await session.flush()
    notify(session, recipient, "pos_visit_cancelled", visit)
    record(session, actor, "cancel", "pos_visits", visit.id, before, snapshot(visit), request)


async def cancel_device_work(session, device, actor, reason, request=None):
    visits = await session.scalars(
        select(PosVisit)
        .where(PosVisit.pos_device_id == device.id, PosVisit.status.in_(OPEN_STATES))
        .with_for_update()
    )
    for visit in visits:
        await cancel_work(session, visit, actor, reason, request)
