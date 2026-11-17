from app.core.text import search_key

REGISTRY_COLUMNS = [
    "device_number",
    "branch_code",
    "owner_name",
    "address",
    "owner_mobile",
    "owner_national_code",
    "shop_name",
    "account_number",
    "contact_phone",
    "status",
]
TRANSACTION_COLUMNS = [
    "device_number",
    "transaction_amount",
    "transaction_count",
    "from_date",
    "to_date",
]
REQUIRED_REGISTRY = {"device_number", "branch_code", "owner_name", "address"}
REQUIRED_TRANSACTION = {"device_number", "transaction_amount", "transaction_count"}
ALIASES = {
    "device_number": ["pos_code"],
    "branch_code": [],
    "owner_name": ["نام مشتری"],
    "owner_mobile": ["شماره همراه"],
    "owner_national_code": ["کد ملی"],
    "shop_name": ["نام فروشگاه"],
    "account_number": ["شماره حساب"],
    "contact_phone": ["شماره تماس"],
    "address": ["آدرس", "ادرس"],
    "transaction_amount": ["sum_of_trans", "sum_of_transactions"],
    "transaction_count": ["counts_of_trans", "count_of_transaction", "count_of_transactions"],
    "from_date": [],
    "to_date": [],
    "status": [],
}


def header_key(value):
    return search_key(str(value or "")).replace("_", " ")


HEADER_MAP = {
    header_key(alias): field for field, aliases in ALIASES.items() for alias in [field, *aliases]
}
IGNORED = {
    header_key(value)
    for value in [
        "طبقه بندی پایانه",
        "performance_classification",
        "performance",
        "terminal_classification",
        "classification",
        "نام شعبه",
        "branch_name",
    ]
}


def template_columns(kind):
    if kind == "devices":
        return REGISTRY_COLUMNS
    if kind == "transactions":
        return TRANSACTION_COLUMNS
    return REGISTRY_COLUMNS + [c for c in TRANSACTION_COLUMNS if c not in REGISTRY_COLUMNS]
