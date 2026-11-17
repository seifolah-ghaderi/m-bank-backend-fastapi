from io import BytesIO

import pytest
from openpyxl import Workbook, load_workbook
from sqlalchemy import func, select

from app.core.errors import DomainError
from app.core.excel import read_xlsx
from app.features.pos.service_imports import prepare, stored_path
from app.models import AuditLog, ImportLog, PosDevice, PosTransaction

REGISTRY = ["device_number", "branch_code", "owner_name", "address", "owner_mobile"]
ACTIVITY = ["device_number", "transaction_amount", "transaction_count"]


@pytest.fixture(autouse=True)
def private_import_storage(api, tmp_path):
    api.settings.import_storage_dir = tmp_path


def xlsx(headers, rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    content = BytesIO()
    workbook.save(content)
    return content.getvalue()


async def upload(
    api, kind, headers=None, rows=None, *, content=None, role="supervisor", month=True
):
    return await api.client.post(
        "/api/v1/pos/imports/" + kind,
        files={
            "file": (
                "synthetic.xlsx",
                content or xlsx(headers, rows),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        data={"jalali_year": "1405", "jalali_month": "7"} if month else {},
        headers=api.headers[role],
    )


async def test_parser_headers_sheets_and_limits(api):
    content = xlsx(["device_number", "pos_code", "branch_code", "owner_name", "address"], [])
    with pytest.raises(DomainError, match="ambiguous_columns"):
        prepare(content, "devices", api.settings)
    with pytest.raises(DomainError, match="missing_columns"):
        prepare(xlsx(["device_number"], []), "devices", api.settings)
    with pytest.raises(DomainError, match="invalid_file"):
        read_xlsx(b"not an excel file", 5000)
    with pytest.raises(DomainError, match="too_many_rows"):
        read_xlsx(xlsx(["a"], [[1], [2]]), 1)
    workbook = Workbook()
    workbook.active.sheet_state = "hidden"
    sheet = workbook.create_sheet("Visible")
    sheet.append(REGISTRY)
    sheet.append([123, 71, "Synthetic Owner", "Synthetic address", "9173094912"])
    sheet["A2"].number_format = "000000"
    sheet["B2"].number_format = "000000"
    output = BytesIO()
    workbook.save(output)
    response = await upload(api, "devices", content=output.getvalue())
    # Numeric branch 71 correctly becomes 000071 rather than guessing another branch.
    assert response.status_code == 200, response.text
    assert response.json()["errors_preview"][0]["error_code"] == "unknown_branch"
    with pytest.raises(DomainError, match="not_found"):
        stored_path(api.settings, "../outside.xlsx")


async def test_registry_aliases_skip_errors_and_ignored_classification(api):
    headers = [
        "pos_code",
        "branch_code",
        "نام مشتری",
        "آدرس",
        "شماره همراه",
        "شماره حساب",
        "طبقه بندی پایانه",
    ]
    rows = [
        [
            "000123",
            api.branches[0].code,
            "Synthetic Owner",
            "Synthetic store address",
            "+9809173094912",
            "001234",
            "ارزشمند",
        ],
        [
            "000124",
            "MISSING",
            "Other Owner",
            "Synthetic address",
            "09173094912",
            "00234",
            "کم کارکرد",
        ],
        [
            "000123",
            api.branches[0].code,
            "Duplicate Owner",
            "Synthetic address",
            "09173094912",
            "00345",
            "",
        ],
    ]
    content = xlsx(headers, rows)
    response = await upload(api, "devices", content=content, month=False)
    assert response.status_code == 200, response.text
    result = response.json()
    assert (result["status"], result["created"], result["failed"]) == (
        "completed_with_errors",
        1,
        2,
    )
    assert [e["error_code"] for e in result["errors_preview"]] == [
        "unknown_branch",
        "duplicate_in_file",
    ]
    assert not result["warnings"]
    async with api.database.sessions() as session:
        device = await session.scalar(select(PosDevice))
        assert device.device_number == "000123" and device.owner_mobile == "09173094912"
        assert device.account_number == "001234" and not hasattr(device, "performance")
    response = await upload(
        api,
        "devices",
        headers,
        [["000123", "BAD", "Changed owner", "x", "invalid mobile", "000", ""]],
        month=False,
    )
    assert response.json()["skipped"] == 1 and response.json()["failed"] == 0
    assert response.json()["status"] == "completed"
    again = await upload(api, "devices", content=content, month=False)
    assert again.json()["duplicate_of"] == result["id"]
    original = await api.client.get(result["file_url"], headers=api.headers["supervisor"])
    assert original.content == content
    assert (
        await api.client.get(result["file_url"], headers=api.headers["manager"])
    ).status_code == 403
    errors = await api.client.get(
        result["errors_url"], params={"format": "xlsx"}, headers=api.headers["supervisor"]
    )
    workbook = load_workbook(BytesIO(errors.content))
    assert workbook.active.max_row == 3
    async with api.database.sessions() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(AuditLog).where(AuditLog.action == "download")
            )
            == 1
        )


async def test_transaction_import_month_upsert_and_errors(api):
    await upload(
        api,
        "devices",
        REGISTRY,
        [["TERM-001", api.branches[0].code, "Synthetic Owner", "Synthetic address", "9173094912"]],
        month=False,
    )
    headers = ["pos_code", "sum_of_trans", "counts_of_trans"]
    response = await upload(api, "transactions", headers, [["TERM-001", "۲۰۰٬۰۰۰٬۰۰۰", 5]])
    assert response.status_code == 200, response.text
    assert response.json()["created"] == 1 and response.json()["period_to"] == "1405/07/30"
    response = await upload(api, "transactions", headers, [["TERM-001", 200000000, 6]])
    assert response.json()["updated"] == 1
    response = await upload(api, "transactions", headers, [["TERM-001", 200000000, 6]])
    assert response.json()["unchanged"] == 1
    response = await upload(
        api,
        "transactions",
        headers + ["from_date", "to_date"],
        [["TERM-001", 100, 2, "1405/07/15", "1405/08/01"], ["UNKNOWN-01", 1, 1, None, None]],
    )
    assert response.status_code == 200, response.text
    assert response.json()["failed"] == 2
    assert response.json()["errors_preview"][0]["error_code"] == "period_mismatch"
    async with api.database.sessions() as session:
        rows = list(await session.scalars(select(PosTransaction)))
        assert len(rows) == 1 and rows[0].transaction_count == 6


async def test_combined_import_atomic_rows_and_existing_skip(api):
    headers = REGISTRY + ["transaction_amount", "transaction_count"]
    rows = [
        [
            "TERM-001",
            api.branches[0].code,
            "Synthetic Owner",
            "Synthetic address",
            "09173094912",
            100,
            1,
        ],
        [
            "TERM-002",
            api.branches[0].code,
            "Synthetic Owner",
            "Synthetic address",
            "09173094912",
            100,
            -1,
        ],
    ]
    response = await upload(api, "combined", headers, rows)
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["created"], data["failed"]) == (1, 1)
    assert data["component_counts"] == {"registry_created": 1, "activity_created": 1}
    async with api.database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(PosDevice)) == 1
        assert await session.scalar(select(func.count()).select_from(PosTransaction)) == 1
    response = await upload(
        api, "combined", headers, [["TERM-001", "IGNORED", "Other Owner", "x", "invalid", 200, 2]]
    )
    assert response.status_code == 200, response.text
    assert response.json()["updated"] == 1
    assert response.json()["component_counts"] == {"registry_skipped": 1, "activity_updated": 1}


async def test_whole_file_rejections_and_templates(api):
    response = await upload(api, "devices", ["device_number"], [["TERM-001"]], month=False)
    assert response.status_code == 422
    response = await upload(api, "devices", content=b"bad data", month=False)
    assert response.status_code == 422
    api.settings.import_max_mb = 1
    response = await upload(api, "devices", content=b"0" * (1024 * 1024 + 1), month=False)
    assert response.status_code == 413
    response = await upload(api, "devices", REGISTRY, [], role="manager", month=False)
    assert response.status_code == 403
    response = await api.client.get(
        "/api/v1/pos/imports/templates/combined", headers=api.headers["supervisor"]
    )
    workbook = load_workbook(BytesIO(response.content))
    headers = [c.value for c in workbook.active[1]]
    assert "device_number" in headers and "transaction_count" in headers
    assert "طبقه بندی پایانه" not in headers
    async with api.database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ImportLog)) == 0


async def test_fault_rolls_back_file_but_keeps_failed_provenance(api, monkeypatch):
    from app.features.pos import service_imports

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic processing failure")

    monkeypatch.setattr(service_imports, "record", fail)
    content = xlsx(
        REGISTRY,
        [["FAIL-001", api.branches[0].code, "Synthetic Owner", "Synthetic address", "09173094912"]],
    )
    with pytest.raises(RuntimeError, match="synthetic processing failure"):
        await service_imports.import_file(
            api.database,
            api.settings,
            api.users["supervisor"],
            "devices",
            content,
            "synthetic.xlsx",
        )
    async with api.database.sessions() as session:
        log = await session.scalar(select(ImportLog))
        assert log.status == "failed" and log.success_count == 0 and log.failure_count == 1
        assert (api.settings.import_storage_dir / log.storage_key).read_bytes() == content
        assert await session.scalar(select(func.count()).select_from(PosDevice)) == 0


async def test_recovery_is_dry_run_and_skips_active_imports(api):
    from datetime import timedelta

    from app.cli import fail_stale_pos_imports
    from app.core import dates

    async with api.database.sessions.begin() as session:
        log = ImportLog(
            import_type="pos_devices",
            mode="create_only",
            file_name="synthetic.xlsx",
            storage_key="synthetic.xlsx",
            file_sha256="a" * 64,
            status="processing",
            started_at=dates.now() - timedelta(hours=2),
            total_rows=2,
        )
        session.add(log)
    (api.settings.import_storage_dir / "orphan.xlsx").write_bytes(b"orphan")
    async with api.database.sessions.begin() as active:
        await active.scalar(select(ImportLog).where(ImportLog.id == log.id).with_for_update())
        result = await fail_stale_pos_imports(
            api.database, api.settings, 60, apply=True, confirm_no_active_imports=True
        )
        assert result["stale_import_ids"] == []
    result = await fail_stale_pos_imports(api.database, api.settings, 60)
    assert result["stale_import_ids"] == [str(log.id)] and result["orphan_files"] == ["orphan.xlsx"]
    async with api.database.sessions() as session:
        assert (await session.get(ImportLog, log.id)).status == "processing"
    with pytest.raises(ValueError):
        await fail_stale_pos_imports(api.database, api.settings, 60, apply=True)
    await fail_stale_pos_imports(
        api.database, api.settings, 60, apply=True, confirm_no_active_imports=True
    )
    async with api.database.sessions() as session:
        saved = await session.get(ImportLog, log.id)
        assert saved.status == "failed" and saved.failure_count == 2
    assert (api.settings.import_storage_dir / "orphan.xlsx").exists()


async def test_sample_shaped_headers_and_native_dates(api):
    from app.core.dates import month_bounds

    headers = [
        "branch_code",
        "نام شعبه",
        "pos_code",
        "شماره حساب",
        "نام مشتری",
        "شماره همراه",
        "شماره تماس",
        "آدرس",
        "طبقه بندی پایانه",
    ]
    response = await upload(
        api,
        "devices",
        headers,
        [
            [
                api.branches[0].code,
                "Synthetic Branch",
                "SAMPLE-001",
                "001234",
                "Synthetic Owner",
                "9173094912",
                "07100000000",
                "Synthetic address",
                "ارزشمند",
            ]
        ],
        month=False,
    )
    assert response.json()["created"] == 1
    start, end = month_bounds(1405, 7)
    response = await upload(
        api,
        "transactions",
        [
            "branch_code",
            "نام شعبه",
            "pos_code",
            "شماره حساب",
            "sum_of_trans",
            "counts_of_trans",
            "from_date",
            "to_date",
        ],
        [[api.branches[0].code, "Synthetic Branch", "SAMPLE-001", "001234", 1000, 5, start, end]],
        month=False,
    )
    assert response.status_code == 200 and response.json()["created"] == 1, response.text
    response = await upload(
        api,
        "transactions",
        ["device_number", "transaction_amount", "transaction_count", "from_date", "to_date"],
        [["SAMPLE-001", 100, 2, "1405/07/15", "1405/08/15"]],
        month=False,
    )
    assert response.json()["errors_preview"][0]["error_code"] == "overlapping_period"
    async with api.database.sessions() as session:
        device = await session.scalar(select(PosDevice))
        assert device.contact_phone == "07100000000"


async def test_empty_required_cells_never_become_text_values(api):
    response = await upload(
        api,
        "devices",
        REGISTRY,
        [["NULL-001", api.branches[0].code, None, "Synthetic address", "09173094912"]],
        month=False,
    )
    assert response.status_code == 200
    error = response.json()["errors_preview"][0]
    assert error["error_code"] == "missing_required" and error["column_name"] == "owner_name"
    assert response.json()["created"] == 0


async def test_numeric_amount_reads_exact_xml_decimal(api):
    from zipfile import ZipFile

    await upload(
        api,
        "devices",
        REGISTRY,
        [
            [
                "EXACT-001",
                api.branches[0].code,
                "Synthetic Owner",
                "Synthetic address",
                "09173094912",
            ]
        ],
        month=False,
    )
    source = xlsx(ACTIVITY, [["EXACT-001", 100.01, 5]])
    output = BytesIO()
    with ZipFile(BytesIO(source)) as original, ZipFile(output, "w") as edited:
        for entry in original.infolist():
            value = original.read(entry.filename)
            if entry.filename == "xl/worksheets/sheet1.xml":
                assert b"<v>100.01</v>" in value
                value = value.replace(b"<v>100.01</v>", b"<v>999999999999999999.99</v>")
            edited.writestr(entry, value)
    response = await upload(api, "transactions", content=output.getvalue())
    assert response.status_code == 200 and response.json()["created"] == 1, response.text
    async with api.database.sessions() as session:
        row = await session.scalar(select(PosTransaction))
        assert str(row.transaction_amount) == "999999999999999999.99"
