from dataclasses import dataclass
from types import SimpleNamespace

from starlette.concurrency import run_in_threadpool

from app.core.errors import DomainError
from app.core.excel import identifier_cell, read_xlsx, workbook_bytes
from app.core.text import search_key

LEAD_MAX_MB = 50
LEAD_MAX_ROWS = 100_000
ORGANIZATION_COLUMNS = ("branch_code", "branch_name", "city")
LEAD_REQUIRED = ("city", "first_name", "last_name", "mobile")
LEAD_COLUMNS = (
    *LEAD_REQUIRED,
    "national_code",
    "occupation",
    "address",
    "referrer",
    "additional_info",
)
LEAD_ALIASES = {
    "شهرستان": "city",
    "نام": "first_name",
    "نام خانوادگی": "last_name",
    "تلفن": "mobile",
    "شماره همراه": "mobile",
    "آدرس": "address",
    "نام فروشگاه": "shop_name",
    "فعالیت": "activity",
}
IGNORED_LEAD_COLUMNS = {"کد", "branch_code", "کد شعبه"}
IDENTIFIERS = {"branch_code", "mobile", "national_code"}


@dataclass(frozen=True)
class WorkbookRows:
    columns: list
    rows: list
    warnings: list
    total_rows: int

    def values(self, cells, fields=None):
        values = {}
        for field, (value, fmt, _) in zip(self.columns, cells, strict=False):
            if field is None or (fields is not None and field not in fields):
                continue
            if field in IDENTIFIERS:
                try:
                    value = identifier_cell(SimpleNamespace(value=value, number_format=fmt))
                except ValueError:
                    code = "invalid_mobile" if field == "mobile" else "invalid_format"
                    raise DomainError(422, code, details={"column": field}) from None
            if isinstance(value, str):
                value = value.strip() or None
            values[field] = value
        return values


def max_bytes(settings, kind):
    return (LEAD_MAX_MB if kind == "leads" else settings.import_max_mb) * 1024 * 1024


def prepare(settings, kind, filename, content, *, count_only=False):
    if len(content) > max_bytes(settings, kind):
        raise DomainError(413, "file_too_large")
    if not filename or not filename.lower().endswith(".xlsx"):
        raise DomainError(422, "invalid_file")
    is_leads = kind == "leads"
    headers, data = read_xlsx(
        content, LEAD_MAX_ROWS if is_leads else settings.import_max_rows, count_only=count_only
    )
    rows, total_rows = ([], data) if count_only else (data, len(data))
    canonical = LEAD_COLUMNS if is_leads else ORGANIZATION_COLUMNS
    mapping = {field: field for field in canonical}
    if is_leads:
        mapping.update({search_key(key): field for key, field in LEAD_ALIASES.items()})
    warnings, columns, used = [], [], set()
    for name in headers:
        key = search_key(name)
        field = mapping.get(key)
        if field:
            if field in used:
                raise DomainError(422, "ambiguous_columns", details={"column": field})
            used.add(field)
        elif key:
            code = (
                "ignored_column" if is_leads and key in IGNORED_LEAD_COLUMNS else "unknown_column"
            )
            warnings.append({"code": code, "column": name})
        columns.append(field)
    required = LEAD_REQUIRED if is_leads else ORGANIZATION_COLUMNS
    missing = sorted(set(required) - used)
    if missing:
        raise DomainError(422, "missing_columns", details={"columns": missing})
    if not total_rows:
        raise DomainError(422, "empty_workbook")
    return WorkbookRows(columns, rows, warnings, total_rows)


async def read_upload(file, settings, kind):
    try:
        content = await file.read(max_bytes(settings, kind) + 1)
    finally:
        await file.close()
    sheet = await run_in_threadpool(
        prepare, settings, kind, file.filename, content, count_only=kind == "leads"
    )
    return content, sheet


def template(kind):
    if kind == "organization":
        return workbook_bytes(ORGANIZATION_COLUMNS, [("007100", "Sample Branch", "Sample City")])
    return workbook_bytes(LEAD_COLUMNS, [("Sample City", "Sample", "Lead", "09120000001")])
