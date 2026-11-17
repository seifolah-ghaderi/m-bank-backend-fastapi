from decimal import Decimal
from uuid import UUID

import jdatetime
from sqlalchemy import case, func, select, true

from app.core import dates
from app.core.errors import DomainError
from app.core.validation import input_values
from app.features.pos.service_devices import device_query, get_device
from app.models import PosPerformanceSettings, PosTransaction
from app.schemas.common import Output
from app.schemas.pos import PosTransactionOut


class PerformanceOut(Output):
    pos_device_id: UUID
    device_number: str
    branch_id: UUID
    status: str
    from_date: dates.JalaliDate
    to_date: dates.JalaliDate
    transaction_amount: Decimal | None
    transaction_count: Decimal | None
    record_count: int
    covered_days: int
    performance: str | None
    no_data: bool
    lower_threshold: Decimal
    upper_threshold: Decimal
    policy_version: int
    last_transaction_period_end: dates.JalaliDate | None
    months_since_last_transaction: int | None = None
    unit: str = "rials"
    method: str = "period_total_amount"


def productivity_query(actor, start, end, **filters):
    devices = device_query(actor, **filters).subquery("scoped_devices")
    totals = select(
        PosTransaction.pos_device_id,
        func.sum(PosTransaction.transaction_amount).label("amount"),
        func.sum(PosTransaction.transaction_count).label("count"),
        func.count().label("records"),
        func.sum(PosTransaction.to_date - PosTransaction.from_date + 1).label("days"),
    ).where(
        PosTransaction.deleted_at.is_(None),
        PosTransaction.from_date >= start,
        PosTransaction.to_date <= end,
        PosTransaction.pos_device_id.in_(select(devices.c.id)),
    )
    totals = totals.group_by(PosTransaction.pos_device_id).subquery("period_totals")
    last = (
        select(func.max(PosTransaction.to_date))
        .where(
            PosTransaction.deleted_at.is_(None),
            PosTransaction.pos_device_id == devices.c.id,
        )
        .correlate(devices)
        .scalar_subquery()
    )
    policy = PosPerformanceSettings
    performance = case(
        (totals.c.records.is_(None), None),
        (totals.c.amount < policy.lower_threshold, "low"),
        (totals.c.amount <= policy.upper_threshold, "normal"),
        else_="high",
    )
    return (
        select(
            devices.c.id.label("pos_device_id"),
            devices.c.device_number,
            devices.c.branch_id,
            devices.c.status,
            totals.c.amount.label("transaction_amount"),
            totals.c.count.label("transaction_count"),
            func.coalesce(totals.c.records, 0).label("record_count"),
            func.coalesce(totals.c.days, 0).label("covered_days"),
            performance.label("performance"),
            totals.c.records.is_(None).label("no_data"),
            policy.lower_threshold,
            policy.upper_threshold,
            policy.policy_version,
            last.label("last_transaction_period_end"),
        )
        .select_from(devices)
        .outerjoin(totals, totals.c.pos_device_id == devices.c.id)
        .join(policy, true())
        .where(policy.id == 1)
    )


def present_performance(row, start, end):
    values = dict(row)
    last = values["last_transaction_period_end"]
    if last is not None:
        a = jdatetime.date.fromgregorian(date=last)
        b = jdatetime.date.fromgregorian(date=dates.today())
        values["months_since_last_transaction"] = max(0, (b.year - a.year) * 12 + b.month - a.month)
    return PerformanceOut(**values, from_date=start, to_date=end)


async def ranking(session, actor, period, params, *, performance=None, no_data=None, **filters):
    start, end = dates.period_range(**input_values(period))
    query = productivity_query(actor, start, end, **filters).subquery("performance_rows")
    statement = select(query)
    if performance is not None:
        statement = statement.where(query.c.performance == performance)
    if no_data is not None:
        statement = statement.where(query.c.no_data == no_data)
    allowed = {
        "transaction_amount": query.c.transaction_amount,
        "productivity": query.c.transaction_amount,
        "transaction_count": query.c.transaction_count,
        "device_number": query.c.device_number,
    }
    sort = params.sort or "transaction_amount"
    column = allowed.get(sort.removeprefix("-"))
    if column is None:
        raise DomainError(422, "invalid_sort")
    total = await session.scalar(select(func.count()).select_from(statement.subquery()))
    order = column.desc() if sort.startswith("-") else column.asc()
    rows = (
        await session.execute(
            statement.order_by(order.nulls_last(), query.c.device_number, query.c.pos_device_id)
            .offset((params.page - 1) * params.page_size)
            .limit(params.page_size)
        )
    ).mappings()
    return {
        "items": [present_performance(r, start, end) for r in rows],
        "total": total,
        "page": params.page,
        "page_size": params.page_size,
    }


async def device_performance(session, actor, device_id, period):
    await get_device(session, device_id, actor)
    start, end = dates.period_range(**input_values(period))
    query = productivity_query(actor, start, end).subquery()
    row = (
        (await session.execute(select(query).where(query.c.pos_device_id == device_id)))
        .mappings()
        .one()
    )
    series = await session.scalars(
        select(PosTransaction)
        .where(
            PosTransaction.pos_device_id == device_id,
            PosTransaction.deleted_at.is_(None),
            PosTransaction.from_date >= start,
            PosTransaction.to_date <= end,
        )
        .order_by(PosTransaction.from_date, PosTransaction.id)
    )
    return {
        **present_performance(row, start, end).model_dump(mode="json"),
        "series": [PosTransactionOut.model_validate(r).model_dump(mode="json") for r in series],
    }
