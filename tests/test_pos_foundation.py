from decimal import Decimal

import pytest
from pydantic import ValidationError


def test_import_settings_are_bounded(settings):
    assert settings.import_max_mb == 10
    assert settings.import_max_rows == 5000
    for field, value in (("import_max_mb", 11), ("import_max_rows", 5001)):
        with pytest.raises(ValidationError):
            type(settings)(_env_file=None, **(settings.model_dump() | {field: value}))


def test_pos_metadata_constraints():
    from sqlalchemy.dialects.postgresql import ExcludeConstraint

    from app.models import PosDevice, PosTransaction, PosVisit

    assert "performance" not in PosDevice.__table__.columns
    assert any(isinstance(c, ExcludeConstraint) for c in PosTransaction.__table__.constraints)
    assert any(i.name == "uq_pos_visits_open" for i in PosVisit.__table__.indexes)


@pytest.mark.parametrize(
    "value",
    [
        "+9809173094912",
        "09173094912",
        "9173094912",
        "+989173094912",
        "009809173094912",
        "989173094912",
        "۰۹۱۷۳۰۹۴۹۱۲",
    ],
)
def test_confirmed_mobile_variants(value):
    from app.core.text import mobile

    assert mobile(value) == "09173094912"


def test_jalali_month_ranges(clock):
    from app.core.dates import format_date, month_bounds, period_range
    from app.core.errors import DomainError

    assert tuple(map(format_date, month_bounds(1405, 7))) == ("1405/07/01", "1405/07/30")
    assert format_date(month_bounds(1403, 12)[1]) == "1403/12/30"
    assert format_date(month_bounds(1404, 12)[1]) == "1404/12/29"
    assert tuple(map(format_date, period_range())) == ("1405/07/01", "1405/07/30")
    for kwargs in (
        {"jalali_year": 1405},
        {"jalali_year": 1405, "jalali_month": 13},
        {"from_date": month_bounds(1402, 1)[0], "to_date": month_bounds(1405, 1)[1]},
    ):
        with pytest.raises(DomainError):
            period_range(**kwargs)


def test_decimal_audit_is_lossless():
    from app.core.audit import present, sanitize
    from app.core.dates import parse_date

    values = {
        "amount": Decimal("999999999999999999.99"),
        "from_date": parse_date("1405/07/01"),
        "password_hash": "secret",
    }
    out = present(sanitize(values))
    assert out == {"amount": "999999999999999999.99", "from_date": "1405/07/01"}
