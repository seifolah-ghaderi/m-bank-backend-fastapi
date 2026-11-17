import re
from contextvars import ContextVar
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

import jdatetime
from pydantic import BeforeValidator, PlainSerializer, WithJsonSchema

from app.core.text import digits

business_timezone = ContextVar("business_timezone", default="Asia/Tehran")


def now() -> datetime:
    return datetime.now(UTC)


def today() -> date:
    return now().astimezone(ZoneInfo(business_timezone.get())).date()


def parse_date(value: str | date) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}/[0-9]{2}/[0-9]{2}", digits(value)):
        raise ValueError("Expected a Jalali YYYY/MM/DD date")
    year, month, day = map(int, digits(value).split("/"))
    if not 1 <= year <= 1500:
        raise ValueError("Jalali year must be between 1 and 1500")
    return jdatetime.date(year, month, day).togregorian()


def format_date(value: date) -> str:
    converted = jdatetime.date.fromgregorian(date=value)
    return f"{converted.year:04}/{converted.month:02}/{converted.day:02}"


def parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("Date-time requires an explicit offset")
        return value.astimezone(UTC)
    match = re.fullmatch(
        r"([0-9]{4}/[0-9]{2}/[0-9]{2})T([0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?)([+-][0-9]{2}:[0-9]{2})",
        digits(value),
    )
    if not match:
        raise ValueError("Expected an offset-bearing Jalali date-time")
    gregorian = parse_date(match[1])
    return datetime.fromisoformat(f"{gregorian.isoformat()}T{match[2]}{match[3]}").astimezone(UTC)


def format_datetime(value: datetime) -> str:
    local = value.astimezone(ZoneInfo(business_timezone.get()))
    return f"{format_date(local.date())}T{local.isoformat().split('T', 1)[1]}"


def day_bound(value: date, *, after: bool = False) -> datetime:
    if after:
        value += timedelta(days=1)
    return datetime.combine(value, time.min, ZoneInfo(business_timezone.get())).astimezone(UTC)


JalaliDate = Annotated[
    date,
    BeforeValidator(parse_date),
    PlainSerializer(format_date),
    WithJsonSchema(
        {"type": "string", "pattern": r"^\d{4}/\d{2}/\d{2}$", "examples": ["1405/08/25"]}
    ),
]
JalaliDateTime = Annotated[
    datetime,
    BeforeValidator(parse_datetime),
    PlainSerializer(format_datetime),
    WithJsonSchema({"type": "string", "examples": ["1405/08/25T09:30:00+03:30"]}),
]


def month_bounds(year: int, month: int) -> tuple[date, date]:
    first = jdatetime.date(year, month, 1)
    following = jdatetime.date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    return first.togregorian(), following.togregorian() - timedelta(days=1)


def period_range(
    *, jalali_year=None, jalali_month=None, from_date=None, to_date=None, default=True
) -> tuple[date, date]:
    """Resolve one explicit month/range, rejecting contradictory/partial input."""
    from app.core.errors import DomainError

    try:
        if jalali_year is not None or jalali_month is not None:
            if jalali_year is None or jalali_month is None:
                raise ValueError("Both year and month are required")
            if not 1 <= jalali_year <= 1500:
                raise ValueError("Invalid Jalali year")
            start, end = month_bounds(jalali_year, jalali_month)
            if (from_date is not None and from_date != start) or (
                to_date is not None and to_date != end
            ):
                raise DomainError(422, "period_mismatch")
        elif from_date is not None or to_date is not None:
            if from_date is None or to_date is None:
                raise ValueError("Both period bounds are required")
            start, end = from_date, to_date
        elif default:
            current = jdatetime.date.fromgregorian(date=today())
            year, month = (
                (current.year - 1, 12) if current.month == 1 else (current.year, current.month - 1)
            )
            start, end = month_bounds(year, month)
        else:
            raise ValueError("Missing period")
        a, b = (jdatetime.date.fromgregorian(date=d) for d in (start, end))
        if end < start or (b.year - a.year) * 12 + b.month - a.month >= 24:
            raise ValueError("Invalid period")
        return start, end
    except (ValueError, TypeError, OverflowError):
        raise DomainError(422, "invalid_period") from None
