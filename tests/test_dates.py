from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from app.core import dates
from app.core.dates import JalaliDate, JalaliDateTime


def test_jalali_round_trip():
    adapter = TypeAdapter(JalaliDate)
    value = adapter.validate_python("۱۴۰۵/۰۸/۲۵")
    assert value.isoformat() == "2026-11-16"
    assert adapter.dump_python(value) == "1405/08/25"
    assert adapter.validate_python("1399/12/30").isoformat() == "2021-03-20"
    for bad in ("1400/12/30", "1405/13/01", "1405/07/31", "2026-11-16"):
        with pytest.raises(ValidationError):
            adapter.validate_python(bad)


def test_datetime_offset_and_schema():
    adapter = TypeAdapter(JalaliDateTime)
    value = adapter.validate_python("۱۴۰۵/۰۸/۲۵T۰۹:۳۰:۰۰+۰۳:۳۰")
    assert value == datetime(2026, 11, 16, 6, tzinfo=UTC)
    assert adapter.dump_python(value) == "1405/08/25T09:30:00+03:30"
    for bad in ("1405/08/25T09:30:00", "2026-11-16T09:30:00+03:30"):
        with pytest.raises(ValidationError):
            adapter.validate_python(bad)
    assert adapter.json_schema().get("format") != "date-time"


def test_business_day(clock):
    clock.value = datetime(2026, 11, 15, 22, tzinfo=UTC)
    assert dates.today().isoformat() == "2026-11-16"
    bound = dates.day_bound(dates.today())
    assert bound == datetime(2026, 11, 15, 20, 30, tzinfo=UTC)
