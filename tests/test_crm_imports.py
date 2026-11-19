from io import BytesIO

import pytest
from openpyxl import Workbook, load_workbook
from sqlalchemy import event, select

from app.core.db import Database
from app.core.errors import DomainError
from app.features.crm_imports import history, workbooks, worker
from app.features.crm_imports.leads import import_lead, lead_rows
from app.models import AuditLog, Branch, City, CrmImportRow, Lead, PosDevice
from app.models.base import new_id
from tests.test_marketing_campaigns import create_campaign

IMPORTS = "/api/v1/imports"


def workbook(headers, *rows):
    book = Workbook()
    sheet = book.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    book.save(output)
    return output.getvalue()


def upload(content, name="synthetic.xlsx"):
    return {"file": (name, content)}


async def test_import_history_original_and_errors(api, tmp_path):
    api.settings.import_storage_dir = tmp_path
    content = workbook(["synthetic"], ["data"])
    supervisor = api.users["supervisor"]
    async with api.database.sessions.begin() as session:
        job = await history.create_log(
            session,
            api.settings,
            supervisor,
            None,
            "organization",
            "synthetic.xlsx",
            content,
            [2, 3],
            [],
        )
        history.add_outcome(session, job, 2, "created")
        history.add_outcome(
            session,
            job,
            3,
            "failed",
            DomainError(422, "invalid_field", details={"column": "=1+1"}),
        )
        job.counts = {"created": 1, "failed": 1}
        history.finish(job)

    url = f"{IMPORTS}/{job.id}"
    headers = api.headers["supervisor"]
    for role in ("manager", "employee"):
        for path in (IMPORTS, url, f"{url}/errors", f"{url}/file"):
            assert (await api.client.get(path, headers=api.headers[role])).status_code == 403
    response = await api.client.get(IMPORTS, headers=headers)
    assert response.json()["items"][0]["id"] == str(job.id)
    detail = (await api.client.get(url, headers=headers)).json()
    assert detail["status"] == "completed_with_errors"
    assert (detail["processed_rows"], detail["success_count"], detail["failure_count"]) == (2, 1, 1)
    errors = await api.client.get(f"{url}/errors", headers=headers)
    assert errors.json()["items"] == [
        {"row_number": 3, "error_code": "invalid_field", "column": "=1+1"}
    ]
    report = await api.client.get(f"{url}/errors?format=xlsx", headers=headers)
    report_sheet = load_workbook(BytesIO(report.content)).active
    assert report_sheet["C2"].data_type == "s"
    assert report_sheet["C2"].value == "'=1+1"
    original = await api.client.get(f"{url}/file", headers=headers)
    assert original.content == content
    assert history.workbook_path(api.settings, job.id).stat().st_mode & 0o077 == 0
    async with api.database.sessions() as session:
        audit = await session.scalar(
            select(AuditLog).where(AuditLog.entity_id == job.id, AuditLog.action == "download")
        )
        assert audit.actor_id == supervisor.id


async def test_import_templates(api):
    for kind, columns in (
        ("organization", workbooks.ORGANIZATION_COLUMNS),
        ("leads", workbooks.LEAD_COLUMNS),
    ):
        path = f"{IMPORTS}/templates/{kind}"
        assert (await api.client.get(path, headers=api.headers["manager"])).status_code == 403
        response = await api.client.get(path, headers=api.headers["supervisor"])
        assert response.status_code == 200
        assert next(load_workbook(BytesIO(response.content)).active.values) == columns
        prepared = workbooks.prepare(api.settings, kind, "template.xlsx", response.content)
        assert len(prepared.rows) == 1


def test_workbook_preflight(settings):
    valid = workbook(
        ["شهرستان", "نام", "نام خانوادگی", "تلفن", "کد"], ["شهر", "اسم", "فامیل", 9120000001, 42]
    )
    sheet = workbooks.prepare(settings, "leads", "incoming.xlsx", valid)
    assert sheet.columns == ["city", "first_name", "last_name", "mobile", None]
    assert sheet.warnings == [{"code": "ignored_column", "column": "کد"}]
    bad = workbook(
        ["city", "first_name", "last_name", "mobile", "تلفن"],
        ["city", "First", "Last", "09120000001"],
    )
    settings.import_max_rows = 1
    settings.import_max_mb = 1
    cases = [
        ("leads", bad, "ambiguous_columns"),
        ("leads", workbook(workbooks.LEAD_REQUIRED), "empty_workbook"),
        ("leads", workbook(["city"]), "missing_columns"),
        ("leads", b"bad content", "invalid_file"),
        ("organization", b" " * (1024 * 1024 + 1), "file_too_large"),
        (
            "organization",
            workbook(workbooks.ORGANIZATION_COLUMNS, [1, "First", "City"], [2, "Second", "City"]),
            "too_many_rows",
        ),
    ]
    for kind, content, code in cases:
        with pytest.raises(DomainError, match=code):
            workbooks.prepare(settings, kind, "incoming.xlsx", content)


async def test_organization_two_pass_with_partial_errors(api, tmp_path):
    api.settings.import_storage_dir = tmp_path
    headers = api.headers["supervisor"]
    await api.client.post(
        "/api/v1/cities", headers=headers, json={"name": "Inactive City", "is_active": False}
    )
    content = workbook(
        workbooks.ORGANIZATION_COLUMNS,
        [7100, "First Office", "اراك"],
        ["007101", "Second Office", "اراک"],
        ["TEH-1", "Branch 1", "تهران"],
        ["TEH-1", "Repeated Office", "تهران"],
        ["TEH-2", "Different Office", "اراک"],
        ["8100", "Inactive Office", "Inactive City"],
        [12.5, "Invalid Code", "Standalone City"],
        ["8100", "Later Duplicate", "اراک"],
    )
    path = f"{IMPORTS}/organization"
    assert (
        await api.client.post(path, headers=api.headers["manager"], files=upload(content))
    ).status_code == 403
    result = await api.client.post(path, headers=headers, files=upload(content))
    assert result.status_code == 200, result.text
    job = result.json()
    assert job["status"] == "completed_with_errors"
    assert (job["created"], job["unchanged"], job["failed"]) == (2, 1, 5)
    assert job["component_counts"] == {"city_created": 2, "city_unchanged": 1, "city_failed": 1}
    errors = await api.client.get(job["errors_url"], headers=headers)
    assert [(row["row_number"], row["error_code"]) for row in errors.json()["items"]] == [
        (5, "duplicate_in_file"),
        (6, "branch_conflict"),
        (7, "inactive_city"),
        (8, "invalid_format"),
        (9, "duplicate_in_file"),
    ]
    async with api.database.sessions() as session:
        city_id = await session.scalar(select(City.id).where(City.name == "اراک"))
        branches = (
            await session.scalars(select(Branch).where(Branch.code.in_(("7100", "007101"))))
        ).all()
        assert len(branches) == 2
        assert {branch.city_id for branch in branches} == {city_id}
    retry = await api.client.post(path, headers=headers, files=upload(content))
    assert (retry.json()["created"], retry.json()["unchanged"]) == (0, 3)


async def test_imported_branch_codes_are_resolved_by_pos(api, tmp_path):
    api.settings.import_storage_dir = tmp_path
    headers = api.headers["supervisor"]
    source = workbook(
        workbooks.ORGANIZATION_COLUMNS,
        [7100, "Numeric Office", "Sample City"],
        [7101, "Padded Office", "Sample City"],
    )
    org_wb = load_workbook(BytesIO(source))
    org_wb.active["A3"].number_format = "000000"
    padded = BytesIO()
    org_wb.save(padded)
    response = await api.client.post(
        f"{IMPORTS}/organization", headers=headers, files=upload(padded.getvalue())
    )
    assert response.json()["created"] == 2
    terminals = workbook(
        ["device_number", "branch_code", "owner_name", "address"],
        ["POS-A", 7100, "Synthetic Owner", "Address"],
        ["POS-B", "007101", "Synthetic Owner", "Address"],
    )
    pos = await api.client.post(
        "/api/v1/pos/imports/devices", headers=headers, files=upload(terminals)
    )
    assert pos.status_code == 200, pos.text
    assert pos.json()["created"] == 2, pos.text
    assert (
        await api.client.get(f"{IMPORTS}/{pos.json()['id']}", headers=headers)
    ).status_code == 404


async def test_lead_registry_accepts_unassigned_but_manual_entry_requires_branch(api):
    async with api.database.sessions.begin() as session:
        lead = Lead(
            city_id=api.city.id, first_name="Imported", last_name="Lead", mobile="09120000021"
        )
        session.add(lead)
        await session.flush()
    headers = api.headers["supervisor"]
    response = await api.client.get(f"/api/v1/leads/{lead.id}", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["branch_id"] is None
    body = {
        "city_id": str(api.city.id),
        "first_name": "Manual",
        "last_name": "Lead",
        "mobile": "09120000022",
    }
    assert (await api.client.post("/api/v1/leads", json=body, headers=headers)).status_code == 422
    result = await api.client.post(
        "/api/v1/leads", json=body | {"branch_id": str(api.branches[0].id)}, headers=headers
    )
    assert result.status_code == 201, result.text
    assert result.json()["branch_id"] == str(api.branches[0].id)


async def test_lead_row_matching_preserves_existing_records(api):
    source = workbook(
        [
            "شهرستان",
            "نام",
            "نام خانوادگی",
            "تلفن",
            "کد",
            "نام فروشگاه",
            "فعالیت",
            "occupation",
            "national_code",
        ],
        [
            "تهران",
            "First",
            "Lead",
            9120000001,
            25,
            "Store",
            "Field work",
            "Unrecognized",
            "0012345679",
        ],
        ["تهران", "Repeat", "Lead", "09120000001"],
        ["تهران", "Landline", "Lead", "02112345678"],
        ["Unknown City", "Unknown", "Lead", "09120000002"],
        ["Inactive City", "Inactive", "Lead", "09120000003"],
    )
    headers = api.headers["supervisor"]
    await api.client.post(
        "/api/v1/cities", headers=headers, json={"name": "Inactive City", "is_active": False}
    )
    sheet = workbooks.prepare(api.settings, "leads", "input.xlsx", source)
    rows = list(lead_rows(sheet))
    assert rows[1][2].code == "duplicate_in_file"
    assert rows[2][2].code == "invalid_mobile"
    values = rows[0][1]
    actor = api.users["supervisor"]
    import_id = new_id()
    async with api.database.sessions.begin() as session:
        assert await import_lead(session, actor, import_id, values) == (
            "created",
            ["unknown_occupation"],
        )
        item = await session.scalar(select(Lead).where(Lead.mobile == "09120000001"))
        assert item.city_id == api.city.id and item.branch_id is None
        assert item.occupation_id is None
        assert item.additional_info == "نام فروشگاه: Store\nفعالیت: Field work"
        item.branch_id = api.branches[0].id
        item.archived_at = api.clock.value
        await session.flush()
        assert await import_lead(session, actor, import_id, values | {"first_name": "Changed"}) == (
            "unchanged",
            ["unknown_occupation"],
        )
        assert item.first_name == "First" and item.branch_id == api.branches[0].id
        assert item.archived_at == api.clock.value
        for _, invalid, code in (
            (*rows[3][:2], "unknown_city"),
            (*rows[4][:2], "inactive_city"),
            (0, values | {"mobile": "09120000004"}, "identity_conflict"),
        ):
            with pytest.raises(DomainError, match=code):
                await import_lead(session, actor, import_id, invalid)


async def test_lead_worker_resumes_and_keeps_ordered_outcomes(api, tmp_path, monkeypatch):
    api.settings.import_storage_dir = tmp_path
    headers = api.headers["supervisor"]
    content = workbook(
        ["شهرستان", "نام", "نام خانوادگی", "کد", "نام فروشگاه", "آدرس", "فعالیت", "تلفن"],
        ["تهران", "First", "Lead", 42, "Synthetic Store", "Address", "Shop", 9120000011],
        ["Unknown City", "Second", "Lead", 43, None, None, None, "09120000012"],
        ["تهران", "Duplicate", "Lead", 42, None, None, None, "09120000011"],
        ["تهران", "Third", "Lead", 44, None, None, None, "09120000013"],
    )
    path = f"{IMPORTS}/leads"
    assert (
        await api.client.post(path, headers=api.headers["employee"], files=upload(content))
    ).status_code == 403
    response = await api.client.post(path, headers=headers, files=upload(content))
    assert response.status_code == 202, response.text
    job = response.json()
    assert job["status"] == "queued" and job["processed_rows"] == 0
    assert job["warnings"] == [{"code": "ignored_column", "column": "کد"}]
    monkeypatch.setattr(worker, "CHUNK_SIZE", 2)
    process_chunk = worker.process_chunk

    async def interrupt(database, job_id, chunk):
        if chunk[0][0] == 4:
            raise RuntimeError("simulated worker interruption")
        await process_chunk(database, job_id, chunk)

    with monkeypatch.context() as stopping:
        stopping.setattr(worker, "process_chunk", interrupt)
        with pytest.raises(RuntimeError, match="simulated worker interruption"):
            await worker.run_one(api.database, api.settings)
    detail = await api.client.get(f"{IMPORTS}/{job['id']}", headers=headers)
    assert detail.json()["status"] == "processing"
    assert detail.json()["processed_rows"] == 2
    assert await worker.run_one(api.database, api.settings) is True
    assert await worker.run_one(api.database, api.settings) is False
    detail = (await api.client.get(f"{IMPORTS}/{job['id']}", headers=headers)).json()
    assert detail["status"] == "completed_with_errors"
    assert (detail["processed_rows"], detail["created"], detail["failed"]) == (4, 2, 2)
    assert detail["started_at"] is not None and detail["finished_at"] is not None
    errors = (await api.client.get(job["errors_url"], headers=headers)).json()["items"]
    assert [(row["row_number"], row["error_code"]) for row in errors] == [
        (3, "unknown_city"),
        (4, "duplicate_in_file"),
    ]
    async with api.database.sessions() as session:
        rows = (await session.scalars(select(CrmImportRow).order_by(CrmImportRow.row_number))).all()
        assert [row.row_number for row in rows] == [2, 3, 4, 5]
        result = (await session.scalars(select(Lead))).all()
        assert {lead.mobile for lead in result} == {"09120000011", "09120000013"}
        assert all(lead.city_id == api.city.id and lead.branch_id is None for lead in result)


async def test_manual_first_branch_assignment_guards(api):
    async with api.database.sessions.begin() as session:
        lead = Lead(
            city_id=api.city.id, first_name="Unassigned", last_name="Lead", mobile="09120000031"
        )
        branch = Branch(code="OFF", name="Inactive Office", city_id=api.city.id, is_active=False)
        session.add_all([lead, branch])
        await session.flush()
    path = f"/api/v1/leads/{lead.id}"
    headers = api.headers["supervisor"]
    target = {"branch_id": str(api.branches[0].id)}
    for role in ("manager", "employee"):
        assert (
            await api.client.post(f"{path}/assign-branch", headers=api.headers[role], json=target)
        ).status_code == 403
    inactive = await api.client.post(
        f"{path}/assign-branch", headers=headers, json={"branch_id": str(branch.id)}
    )
    assert inactive.json()["error"]["code"] == "branch_inactive"
    await api.client.post(f"{path}/archive", headers=headers)
    archived = await api.client.post(f"{path}/assign-branch", headers=headers, json=target)
    assert archived.json()["error"]["code"] == "lead_archived"
    await api.client.post(f"{path}/restore", headers=headers)
    results = await api.client.get("/api/v1/leads?unassigned=true", headers=headers)
    assert [item["id"] for item in results.json()["items"]] == [str(lead.id)]
    for _ in range(2):
        assigned = await api.client.post(f"{path}/assign-branch", headers=headers, json=target)
        assert assigned.status_code == 200, assigned.text
        assert assigned.json()["branch_id"] == target["branch_id"]
        assert assigned.json()["city_id"] == str(api.city.id)
    results = await api.client.get("/api/v1/leads?unassigned=true", headers=headers)
    assert results.json()["total"] == 0
    changed = await api.client.post(
        f"{path}/assign-branch", headers=headers, json={"branch_id": str(api.branches[1].id)}
    )
    assert changed.json()["error"]["code"] == "lead_branch_already_assigned"
    clear = await api.client.post(
        f"{path}/assign-branch", headers=headers, json={"branch_id": None}
    )
    assert clear.status_code == 422
    async with api.database.sessions() as session:
        audit = await session.scalar(
            select(AuditLog).where(
                AuditLog.entity_id == lead.id, AuditLog.action == "assign_branch"
            )
        )
        assert audit.after == target


@pytest.fixture
async def runtime_database(api):
    runtime = Database(api.database.engine.url.render_as_string(hide_password=False))

    @event.listens_for(runtime.engine.sync_engine, "connect")
    def set_role(connection, _):
        cursor = connection.cursor()
        cursor.execute("SET ROLE crm_runtime")
        cursor.close()
        connection.commit()

    api.app.state.database = runtime
    try:
        yield runtime
    finally:
        api.app.state.database = api.database
        await runtime.close()


async def test_imported_organization_leads_and_campaign(api, tmp_path, runtime_database):
    api.settings.import_storage_dir = tmp_path
    client = api.client
    headers = api.headers["supervisor"]
    directory = workbook(
        workbooks.ORGANIZATION_COLUMNS,
        ["0061", "North Office", "Imported City"],
        ["0062", "South Office", "Imported City"],
        ["0061", "Conflicting Office", "Imported City"],
    )
    org = await client.post(f"{IMPORTS}/organization", headers=headers, files=upload(directory))
    assert org.status_code == 200, org.text
    assert org.json()["created"] == 2 and org.json()["failed"] == 1
    branch_list = (await client.get("/api/v1/branches", headers=headers)).json()["items"]
    branch = next(item for item in branch_list if item["code"] == "0061")
    branch_id = branch["id"]

    terminals = workbook(
        ["device_number", "branch_code", "owner_name", "address"],
        ["POS-CRM", "0061", "Synthetic Owner", "Sample Street"],
    )
    pos = await client.post("/api/v1/pos/imports/devices", headers=headers, files=upload(terminals))
    assert pos.json()["created"] == 1, pos.text
    async with api.database.sessions() as session:
        device = await session.scalar(select(PosDevice).where(PosDevice.device_number == "POS-CRM"))
        assert str(device.branch_id) == branch_id

    source = workbook(
        workbooks.LEAD_REQUIRED,
        ["Imported City", "Ready", "Lead", "09120000041"],
        ["Imported City", "Invalid", "Mobile", "02112345678"],
        ["Unknown City", "Unknown", "Lead", "09120000042"],
    )
    uploaded = await client.post(f"{IMPORTS}/leads", headers=headers, files=upload(source))
    assert uploaded.status_code == 202, uploaded.text
    assert await worker.run_one(runtime_database, api.settings)
    status_url = f"{IMPORTS}/{uploaded.json()['id']}"
    job = (await client.get(status_url, headers=headers)).json()
    assert job["status"] == "completed_with_errors"
    assert job["created"] == 1 and job["failed"] == 2
    result = (await client.get("/api/v1/leads?unassigned=true", headers=headers)).json()
    (lead,) = result["items"]
    assert lead["city_id"] == branch["city"]["id"]
    assert lead["branch_id"] is None

    campaign = await create_campaign(api, [])
    preview_path = campaign + "/selection/preview"
    select_path = campaign + "/selection"
    assert (await client.get(preview_path, headers=headers)).json()["total"] == 0
    assert (await client.post(select_path, headers=headers, json={"filters": {}})).json()[
        "added"
    ] == 0
    explicit = await client.post(select_path, headers=headers, json={"lead_ids": [lead["id"]]})
    assert explicit.status_code == 422
    assert explicit.json()["error"]["code"] == "ineligible_lead_selection"

    assign = await client.post(
        f"/api/v1/leads/{lead['id']}/assign-branch", headers=headers, json={"branch_id": branch_id}
    )
    assert assign.status_code == 200, assign.text
    assert (await client.get(preview_path, headers=headers)).json()["total"] == 1
    assert (await client.post(select_path, headers=headers, json={"filters": {}})).json()[
        "added"
    ] == 1

    branch_url = f"/api/v1/branches/{branch_id}"
    await client.patch(branch_url, headers=headers, json={"is_active": False})
    inactive = await client.post(campaign + "/activate", headers=headers)
    assert inactive.status_code == 409
    assert inactive.json()["error"]["code"] == "ineligible_lead_selection"
    await client.patch(branch_url, headers=headers, json={"is_active": True})
    activated = await client.post(campaign + "/activate", headers=headers)
    assert activated.status_code == 200, activated.text
    (assigned,) = (await client.get(f"{campaign}/leads", headers=headers)).json()["items"]
    assert assigned["branch_id"] == branch_id
    assert (
        await client.get(f"{campaign}/leads", headers=api.headers["employee"])
    ).status_code == 404
