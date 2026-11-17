import hashlib
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import SimpleNamespace

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core import dates
from app.core.audit import record
from app.core.db import integrity_error, transaction
from app.core.errors import DomainError
from app.core.excel import identifier_cell, read_xlsx, workbook_bytes
from app.core.lifecycle import lifecycle_actor
from app.core.text import digits, normalize_text
from app.features.pos.import_columns import (
    HEADER_MAP,
    IGNORED,
    REQUIRED_REGISTRY,
    REQUIRED_TRANSACTION,
    header_key,
    template_columns,
)
from app.features.pos.service_devices import create_device
from app.features.pos.service_transactions import transaction_actor, write_transaction
from app.models import Branch, ImportLog, ImportRowError, PosDevice
from app.models.base import new_id
from app.schemas.pos import PosDeviceCreate, PosTransactionCreate, device_number

IDENTIFIERS = {
    "device_number",
    "branch_code",
    "account_number",
    "owner_mobile",
    "owner_national_code",
    "contact_phone",
}


def prepare(content, kind, settings, month=None):
    headers, rows = read_xlsx(content, settings.import_max_rows)
    columns, warnings, used = [], [], set()
    for name in headers:
        key = header_key(name)
        field = HEADER_MAP.get(key)
        if field in used:
            raise DomainError(422, "ambiguous_columns", details={"column": field})
        if field:
            used.add(field)
        elif key not in IGNORED:
            warnings.append({"code": "unknown_column", "column": name})
        columns.append(field)
    required = set()
    if kind in {"devices", "combined"}:
        required |= REQUIRED_REGISTRY
    if kind in {"transactions", "combined"}:
        required |= REQUIRED_TRANSACTION
        if month is None:
            required |= {"from_date", "to_date"}
    missing = sorted(required - used)
    if missing:
        raise DomainError(422, "missing_columns", details={"columns": missing})
    return headers, columns, rows, warnings


def raw_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def row_values(headers, columns, cells):
    raw = {
        header: raw_value(cells[i][0]) if i < len(cells) else None
        for i, header in enumerate(headers)
    }
    values = {}
    for field, data in zip(columns, cells, strict=False):
        if field is None:
            continue
        value, fmt, cell_type = data
        if field in IDENTIFIERS:
            try:
                value = identifier_cell(SimpleNamespace(value=value, number_format=fmt))
            except ValueError:
                raise DomainError(422, "invalid_format", details={"column": field}) from None
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                value = None
        values[field] = value
    return values, raw


def number(value, *, count=False):
    try:
        if isinstance(value, bool) or value is None:
            raise ValueError()
        value = (
            digits(str(value)).replace(",", "").replace("٬", "").replace("٫", ".").replace(" ", "")
        )
        result = Decimal(value)
        if not result.is_finite() or result < 0:
            raise ValueError()
        if count:
            if result != result.to_integral_value() or result > 9223372036854775807:
                raise ValueError()
            return int(result)
        if result.as_tuple().exponent < -2 or result >= 10**18:
            raise ValueError()
        return result
    except (InvalidOperation, ValueError, TypeError):
        raise DomainError(422, "invalid_count" if count else "invalid_amount") from None


def row_period(values, month):
    a, b = values.get("from_date"), values.get("to_date")
    if a is not None or b is not None:
        try:
            a = a.date() if isinstance(a, datetime) else dates.parse_date(a)
            b = b.date() if isinstance(b, datetime) else dates.parse_date(b)
        except (ValueError, TypeError):
            raise DomainError(422, "invalid_period") from None
        if month is not None and (a, b) != month:
            raise DomainError(422, "period_mismatch")
        return a, b
    if month is None:
        raise DomainError(422, "invalid_period")
    return month


def stored_path(settings, key):
    root = settings.import_storage_dir.resolve()
    path = (root / key).resolve()
    if not path.is_relative_to(root) or path == root:
        raise DomainError(404, "not_found")
    return path


async def registry_row(session, actor, values, import_id, request):
    code = device_number(values.get("device_number") or "")
    device = await session.scalar(
        select(PosDevice).where(PosDevice.device_number == code, PosDevice.deleted_at.is_(None))
    )
    if device:
        return device, "skipped"
    if await session.scalar(select(PosDevice.id).where(PosDevice.device_number == code)):
        raise DomainError(422, "device_deleted")
    for field in ("branch_code", "owner_name", "address"):
        if values.get(field) is None:
            raise DomainError(422, "missing_required", details={"column": field})
    branch_code = normalize_text(values.get("branch_code") or "").upper()
    branch = await session.scalar(
        select(Branch).where(Branch.code == branch_code, Branch.deleted_at.is_(None))
    )
    if branch is None:
        raise DomainError(422, "unknown_branch", details={"column": "branch_code"})
    if not branch.is_active:
        raise DomainError(422, "inactive_branch", details={"column": "branch_code"})
    fields = {
        key: values[key]
        for key in PosDeviceCreate.model_fields
        if key in values and (values[key] is not None or key in {"owner_name", "address"})
    }
    body = PosDeviceCreate(**(fields | {"device_number": code, "branch_id": branch.id}))
    return await create_device(
        session, actor, body, request, source="import", import_id=import_id
    ), "created"


async def import_file(
    database,
    settings,
    actor,
    kind,
    content,
    filename,
    request=None,
    *,
    jalali_year=None,
    jalali_month=None,
    mode=None,
):
    if kind not in {"devices", "transactions", "combined"}:
        raise DomainError(404, "not_found")
    modes = {"devices": "create_only", "transactions": "upsert", "combined": "combined"}
    if mode is not None and mode != modes[kind]:
        raise DomainError(422, "invalid_mode")
    if len(content) > settings.import_max_mb * 1024 * 1024:
        raise DomainError(413, "file_too_large")
    if not filename or not filename.lower().endswith(".xlsx"):
        raise DomainError(422, "invalid_file")
    month = None
    if jalali_year is not None or jalali_month is not None:
        month = dates.period_range(
            jalali_year=jalali_year, jalali_month=jalali_month, default=False
        )
    headers, columns, rows, warnings = prepare(content, kind, settings, month)
    import_id, storage_key = new_id(), str(new_id()) + ".xlsx"
    path = stored_path(settings, storage_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    checksum = hashlib.sha256(content).hexdigest()
    async with transaction(database) as session:
        current = await transaction_actor(session, actor)
        duplicate = await session.scalar(
            select(ImportLog.id)
            .where(ImportLog.file_sha256 == checksum)
            .order_by(ImportLog.started_at.desc(), ImportLog.id.desc())
            .limit(1)
        )
        session.add(
            ImportLog(
                id=import_id,
                import_type="pos_" + kind,
                mode=modes[kind],
                file_name=Path(filename.replace("\\", "/")).name[:255],
                storage_key=storage_key,
                file_sha256=checksum,
                status="processing",
                period_from=month[0] if month else None,
                period_to=month[1] if month else None,
                created_by=current.id,
                updated_by=current.id,
                started_at=dates.now(),
                total_rows=len(rows),
            )
        )
    try:
        async with transaction(database) as session:
            current = await (
                lifecycle_actor(session, actor, "supervisor")
                if kind != "transactions"
                else transaction_actor(session, actor)
            )
            log = await session.scalar(
                select(ImportLog).where(ImportLog.id == import_id).with_for_update()
            )
            # Prelock device IDs in one stable order, before per-row writes.
            codes = set()
            for _, cells in rows:
                for i, field in enumerate(columns):
                    if field == "device_number" and i < len(cells):
                        try:
                            codes.add(
                                device_number(
                                    identifier_cell(
                                        SimpleNamespace(
                                            value=cells[i][0], number_format=cells[i][1]
                                        )
                                    )
                                    or ""
                                )
                            )
                        except (ValueError, TypeError):
                            pass
            if codes:
                await session.execute(
                    select(PosDevice.id)
                    .where(PosDevice.device_number.in_(codes))
                    .order_by(PosDevice.id)
                    .with_for_update()
                )
            seen, outcomes, components = set(), Counter(), Counter()
            for row_number, cells in rows:
                raw = {
                    h: raw_value(cells[i][0]) if i < len(cells) else None
                    for i, h in enumerate(headers)
                }
                try:
                    async with session.begin_nested():
                        values, raw = row_values(headers, columns, cells)
                        if not values.get("device_number"):
                            raise DomainError(
                                422, "missing_required", details={"column": "device_number"}
                            )
                        code = device_number(values.get("device_number") or "")
                        bounds = row_period(values, month) if kind != "devices" else None
                        key = (code, *bounds) if bounds else (code,)
                        if key in seen:
                            raise DomainError(422, "duplicate_in_file")
                        seen.add(key)
                        registry_result = None
                        if kind != "transactions":
                            device, registry_result = await registry_row(
                                session, current, values, import_id, request
                            )
                        else:
                            device = await session.scalar(
                                select(PosDevice).where(
                                    PosDevice.device_number == code, PosDevice.deleted_at.is_(None)
                                )
                            )
                            if device is None:
                                raise DomainError(422, "unknown_device")
                        activity_result = None
                        if kind != "devices":
                            for field in ("transaction_amount", "transaction_count"):
                                if values.get(field) is None:
                                    raise DomainError(
                                        422, "missing_required", details={"column": field}
                                    )
                            body = PosTransactionCreate(
                                from_date=bounds[0],
                                to_date=bounds[1],
                                transaction_amount=number(values.get("transaction_amount")),
                                transaction_count=number(
                                    values.get("transaction_count"), count=True
                                ),
                            )
                            _, activity_result = await write_transaction(
                                session,
                                current,
                                device.id,
                                body,
                                request,
                                import_id=import_id,
                                upsert=True,
                            )
                            supplied_branch = values.get("branch_code")
                            if supplied_branch:
                                branch = await session.get(Branch, device.branch_id)
                                if normalize_text(supplied_branch).upper() != branch.code:
                                    warnings.append(
                                        {
                                            "row_number": row_number,
                                            "code": "branch_mismatch_ignored",
                                        }
                                    )
                        await session.flush()
                    outcomes[activity_result or registry_result] += 1
                    if registry_result:
                        components["registry_" + registry_result] += 1
                    if activity_result:
                        components["activity_" + activity_result] += 1
                except (DomainError, ValidationError, ValueError, IntegrityError) as error:
                    outcomes["failed"] += 1
                    if isinstance(error, IntegrityError):
                        error = integrity_error(error)
                    column = None
                    code = error.code if isinstance(error, DomainError) else "invalid_format"
                    if isinstance(error, ValidationError):
                        first = error.errors()[0]
                        column = ".".join(map(str, first["loc"]))
                        if first["type"] == "missing":
                            code = "missing_required"
                        elif str(first.get("ctx", {}).get("error", "")) == "invalid_national_code":
                            code = "invalid_national_code"
                    elif isinstance(error, DomainError) and isinstance(error.details, dict):
                        column = error.details.get("column")
                    session.add(
                        ImportRowError(
                            import_id=import_id,
                            row_number=row_number,
                            column_name=column,
                            error_code=code,
                            message=code.replace("_", " ").capitalize(),
                            raw_data=raw,
                        )
                    )
            for name in ("created", "updated", "unchanged", "skipped"):
                setattr(log, name + "_count", outcomes[name])
            log.failure_count = outcomes["failed"]
            log.success_count = len(rows) - log.failure_count
            log.component_counts = dict(components)
            log.warnings = warnings
            log.status = (
                ("completed_with_errors" if log.success_count else "failed")
                if log.failure_count
                else "completed"
            )
            log.finished_at, log.updated_by = dates.now(), current.id
            await session.flush()
            record(
                session,
                current,
                "import",
                "import_logs",
                import_id,
                after={"status": log.status, "counts": dict(outcomes)},
                request=request,
            )
        return import_id, duplicate
    except BaseException:
        async with transaction(database) as session:
            log = await session.get(ImportLog, import_id)
            log.status, log.finished_at = "failed", dates.now()
            log.failure_count = log.total_rows
            log.success_count = log.created_count = log.updated_count = log.unchanged_count = (
                log.skipped_count
            ) = 0
            log.component_counts = {}
            log.warnings = [{"code": "processing_failed"}]
        raise


def template(kind):
    headers = template_columns(kind)
    example = {
        "device_number": "POS-001",
        "branch_code": "007100",
        "owner_name": "Synthetic Owner",
        "address": "Synthetic store address",
        "owner_mobile": "09173094912",
        "status": "active",
        "transaction_amount": "1000000.00",
        "transaction_count": 5,
        "from_date": "1405/07/01",
        "to_date": "1405/07/30",
    }
    return workbook_bytes(headers, [[example.get(h) for h in headers]])


async def get_log(session, import_id):
    log = await session.get(ImportLog, import_id)
    if log is None:
        raise DomainError(404, "not_found")
    return log


async def log_out(session, log, duplicate=None):
    from app.schemas.pos import ImportLogOut, ImportRowErrorOut

    values = {key: getattr(log, key) for key in ImportLogOut.model_fields if hasattr(log, key)}
    for key in ("created", "updated", "unchanged", "skipped"):
        values[key] = getattr(log, key + "_count")
    errors = await session.scalars(
        select(ImportRowError)
        .where(ImportRowError.import_id == log.id)
        .order_by(ImportRowError.row_number, ImportRowError.id)
        .limit(20)
    )
    return ImportLogOut(
        **values,
        failed=log.failure_count,
        duplicate_of=duplicate,
        errors_preview=[ImportRowErrorOut.model_validate(e) for e in errors],
        errors_url=f"/api/v1/pos/imports/{log.id}/errors",
        file_url=f"/api/v1/pos/imports/{log.id}/file",
    )


async def list_logs(
    session, params, import_type=None, status=None, user_id=None, from_date=None, to_date=None
):
    from app.core.pagination import paginate

    statement = select(ImportLog)
    if import_type:
        statement = statement.where(ImportLog.import_type == import_type)
    if status:
        statement = statement.where(ImportLog.status == status)
    if user_id:
        statement = statement.where(ImportLog.created_by == user_id)
    if from_date:
        statement = statement.where(ImportLog.started_at >= dates.day_bound(from_date))
    if to_date:
        statement = statement.where(ImportLog.started_at < dates.day_bound(to_date, after=True))
    page = await paginate(
        session,
        statement,
        params,
        {"started_at": ImportLog.started_at},
        "-started_at",
        ImportLog.id,
    )
    page["items"] = [await log_out(session, log) for log in page["items"]]
    return page


async def error_report(session, import_id):
    await get_log(session, import_id)
    errors = list(
        await session.scalars(
            select(ImportRowError)
            .where(ImportRowError.import_id == import_id)
            .order_by(ImportRowError.row_number, ImportRowError.id)
        )
    )
    columns = list(dict.fromkeys(key for e in errors for key in e.raw_data))
    return workbook_bytes(
        [*columns, "row_number", "error_code", "error"],
        [
            [e.raw_data.get(key) for key in columns] + [e.row_number, e.error_code, e.message]
            for e in errors
        ],
    )
