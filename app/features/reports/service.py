from datetime import timedelta

import jdatetime
from sqlalchemy import func, select

from app.core import dates
from app.core.deps import scope_for
from app.core.errors import DomainError
from app.models import PosDevice, PosTag, PosTransaction, PosVisit, PosVisitTagLink


async def summary(session, actor, branch_id=None):
    if branch_id is not None and actor.role != "supervisor" and branch_id != actor.branch_id:
        raise DomainError(403, "forbidden")
    visits = scope_for(actor).apply(select(PosVisit), PosVisit)
    if branch_id is not None:
        visits = visits.where(PosVisit.branch_id == branch_id)
    v = visits.subquery("scoped_visits")
    start = dates.day_bound(dates.today() - timedelta(days=29))
    end = dates.day_bound(dates.today(), after=True)
    recent = (v.c.status == "completed") & (v.c.completed_at >= start) & (v.c.completed_at < end)
    counts = (
        (
            await session.execute(
                select(
                    func.count()
                    .filter(v.c.status == "pending_assignment")
                    .label("pending_assignment"),
                    func.count().filter(v.c.status == "assigned").label("assigned"),
                    func.count()
                    .filter((v.c.status == "assigned") & (v.c.due_date < dates.today()))
                    .label("overdue"),
                    func.count().filter(recent).label("completed_in_30_days"),
                ).select_from(v)
            )
        )
        .mappings()
        .one()
    )
    result = dict(counts)
    result["visits_by_result"] = {
        key: count
        for key, count in (
            await session.execute(
                select(v.c.result, func.count()).where(recent).group_by(v.c.result)
            )
        ).all()
    }
    result["tag_counts"] = {
        key: count
        for key, count in (
            await session.execute(
                select(PosTag.code, func.count())
                .select_from(v)
                .join(PosVisitTagLink, PosVisitTagLink.pos_visit_id == v.c.id)
                .join(PosTag, PosTag.id == PosVisitTagLink.tag_id)
                .where(recent, PosVisitTagLink.is_active.is_(True))
                .group_by(PosTag.code)
            )
        ).all()
    }
    result["window_from"] = dates.format_date(dates.today() - timedelta(days=29))
    result["window_to"] = dates.format_date(dates.today())
    if actor.role == "employee":
        result.pop("pending_assignment")
        return result
    devices = scope_for(actor).apply(
        select(PosDevice).where(PosDevice.deleted_at.is_(None)), PosDevice
    )
    if branch_id is not None:
        devices = devices.where(PosDevice.branch_id == branch_id)
    d = devices.subquery("scoped_devices")
    result["devices_by_status"] = {
        s: 0 for s in ("active", "inactive", "under_maintenance", "retired")
    }
    result["devices_by_status"].update(
        {
            key: count
            for key, count in (
                await session.execute(select(d.c.status, func.count()).group_by(d.c.status))
            ).all()
        }
    )
    if actor.role == "supervisor":
        result["devices_per_branch"] = {
            str(key): count
            for key, count in (
                await session.execute(select(d.c.branch_id, func.count()).group_by(d.c.branch_id))
            ).all()
        }
    today = jdatetime.date.fromgregorian(date=dates.today())
    month_index = today.year * 12 + today.month - 1 - 3
    range_start = dates.month_bounds(month_index // 12, month_index % 12 + 1)[0]
    range_end = dates.month_bounds(today.year, today.month)[0] - timedelta(days=1)
    has_recent = (
        select(PosTransaction.id)
        .where(
            PosTransaction.pos_device_id == d.c.id,
            PosTransaction.deleted_at.is_(None),
            PosTransaction.to_date >= range_start,
            PosTransaction.to_date <= range_end,
        )
        .exists()
    )
    result["devices_no_transactions_in_last_3_months"] = await session.scalar(
        select(func.count()).select_from(d).where(~has_recent)
    )
    result["transaction_recency_from"] = dates.format_date(range_start)
    result["transaction_recency_to"] = dates.format_date(range_end)
    return result
