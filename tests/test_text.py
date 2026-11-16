import pytest

from app.core.text import digits, masked_mobile, mobile, national_code, normalize_text, search_key


@pytest.mark.parametrize(
    "value",
    [
        "09123456789",
        "+98 912-345-6789",
        "00989123456789",
        "989123456789",
        "۰۹۱۲۳۴۵۶۷۸۹",
        "٠٩١٢٣٤٥٦٧٨٩",
    ],
)
def test_mobile_normalization(value):
    assert mobile(value) == "09123456789"


@pytest.mark.parametrize(
    "value", ["0912", "009809123456789", "08123456789", "091234567890", "0912345678x"]
)
def test_invalid_mobiles(value):
    with pytest.raises(ValueError, match="invalid_mobile"):
        mobile(value)


@pytest.mark.parametrize("value", ["0000000000", "1111111111", "0012345678", "123", "012345678x"])
def test_bad_national_codes(value):
    with pytest.raises(ValueError, match="invalid_national_code"):
        national_code(value)


def test_valid_code_and_text():
    assert national_code("۰۰۱۲۳۴۵۶۷۹") == "0012345679"
    assert normalize_text("  علي\u200c   كريمي ۱۲ ") == "علی کریمی 12"
    assert search_key("  ABC  ") == "abc"
    assert digits("۱۲٣") == "123"
    assert masked_mobile("09123456789") == "0912***6789"
