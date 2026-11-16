import re

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def digits(value: str) -> str:
    return str(value).translate(_DIGITS)


def normalize_text(value: str) -> str:
    value = digits(value).translate(str.maketrans({"ي": "ی", "ك": "ک"}))
    value = re.sub("[\u200b-\u200f\ufeff]", "", value)
    return " ".join(value.split())


def search_key(value: str) -> str:
    return normalize_text(value).casefold()


def mobile(value: str) -> str:
    value = re.sub(r"[\s-]", "", digits(value))
    for prefix in ("+98", "0098", "98"):
        if value.startswith(prefix):
            value = "0" + value[len(prefix) :]
            break
    if not re.fullmatch(r"09[0-9]{9}", value):
        raise ValueError("invalid_mobile")
    return value


def national_code(value: str) -> str:
    value = digits(value).strip()
    if not re.fullmatch(r"[0-9]{10}", value) or len(set(value)) == 1:
        raise ValueError("invalid_national_code")
    remainder = sum(int(value[i]) * (10 - i) for i in range(9)) % 11
    check = remainder if remainder < 2 else 11 - remainder
    if int(value[-1]) != check:
        raise ValueError("invalid_national_code")
    return value


def masked_mobile(value: str) -> str:
    return value[:4] + "***" + value[-4:]
