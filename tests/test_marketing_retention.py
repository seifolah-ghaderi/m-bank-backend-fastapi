import asyncio
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session as SyncSession

from app.core import dates
from app.core.errors import DomainError
from app.models import AuditLog
from tests.test_marketing_campaigns import create_lead, make_employee
from tests.test_marketing_sales import (
    decide,
    evidence,
    product,
    register,
    schedule,
    start_visit,
    submit,
)

TASKS = "/api/v1/retention-tasks"


async def convert_customer(api, *, number=1, branch=0, employee="employee"):
    lead = await create_lead(api, number, branch)
    _, _, visit = await start_visit(api, lead, employee=employee)
    sale = await register(
        api, visit, await product(api, f"RET{number}"), code=f"530{number}", employee=employee
    )
    submitted = await submit(api, [sale], role=employee)
    assert submitted.status_code == 200, submitted.text
    approved = await decide(api, sale, (await evidence(api))[sale]["id"])
    assert approved.status_code == 200, approved.text
    return approved.json()["customer"]


async def list_tasks(api, role, **params):
    response = await api.client.get(TASKS, headers=api.headers[role], params=params)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
async def open_retention_task(api):
    schedule_response = await schedule(api, 15)
    assert schedule_response.status_code == 201, schedule_response.text
    await convert_customer(api)
    (task,) = (await list_tasks(api, "employee"))["items"]
    return f"{TASKS}/{task['id']}"


async def test_retention_workflow_and_scoped_views(api):
    for offset in (45, 15):
        scheduled = await schedule(api, offset)
        assert scheduled.status_code == 201, scheduled.text
    local = await convert_customer(api)
    foreign = await convert_customer(api, number=2, branch=1, employee="other")
    await make_employee(api)

    employee_page = await list_tasks(api, "employee")
    assert employee_page["total"] == 2
    assert [
        (task["customer_id"], task["due_date"], task["status"]) for task in employee_page["items"]
    ] == [
        (local["id"], dates.format_date(dates.today() + timedelta(days=offset)), "open")
        for offset in (15, 45)
    ]
    first, second = employee_page["items"]
    paged = await list_tasks(api, "employee", page=2, page_size=1)
    assert paged["total"] == 2 and paged["items"] == [second]
    assert (await list_tasks(api, "manager"))["items"] == [first, second]
    assert (await list_tasks(api, "second"))["total"] == 0

    organization = await list_tasks(api, "supervisor")
    assert organization["total"] == 4
    foreign_task = next(
        task for task in organization["items"] if task["customer_id"] == foreign["id"]
    )
    foreign_url = f"{TASKS}/{foreign_task['id']}"
    url = f"{TASKS}/{first['id']}"
    for role, path in (("manager", foreign_url), ("second", url), ("other", url)):
        response = await api.client.get(path, headers=api.headers[role])
        assert response.status_code == 404 and "customer" not in response.json()
    for role in ("employee", "manager", "supervisor"):
        visible = await api.client.get(url, headers=api.headers[role])
        assert visible.status_code == 200, visible.text
        detail = visible.json()
        assert detail["customer"] == {
            key: local[key] for key in ("first_name", "last_name", "phone", "address", "city_id")
        }
        assert {"account_number", "customer_code", "proof_text"}.isdisjoint(detail)
        assert detail["completed_at"] is None

    body = {
        "visit_date": dates.format_date(dates.today()),
        "result": "  Reached customer  ",
        "notes": "Discussed service follow-up.",
    }
    for role, code in (("supervisor", 403), ("manager", 403), ("second", 404), ("other", 404)):
        refused = await api.client.post(url + "/complete", headers=api.headers[role], json=body)
        assert refused.status_code == code, refused.text
    completed = await api.client.post(url + "/complete", headers=api.headers["employee"], json=body)
    assert completed.status_code == 200, completed.text
    result = completed.json()
    assert result["status"] == "completed"
    assert result["visit_date"] == body["visit_date"]
    assert result["result"] == "Reached customer" and result["notes"] == body["notes"]
    assert result["completed_by"] == str(api.users["employee"].id)
    assert result["completed_at"] == dates.format_datetime(api.clock.value)
    assert (await list_tasks(api, "employee"))["items"] == [second]
    for role in ("employee", "manager"):
        (history,) = (await list_tasks(api, role, status="completed"))["items"]
        assert (history["id"], history["result"]) == (first["id"], "Reached customer")
    detail = await api.client.get(url, headers=api.headers["manager"])
    assert detail.json() == result


async def test_retention_completion_validation_and_concurrency(api, open_retention_task):
    url = open_retention_task
    headers = api.headers["employee"]
    body = {"visit_date": dates.format_date(dates.today()), "result": "Reached"}
    tomorrow = dates.format_date(dates.today() + timedelta(days=1))
    for invalid in (
        {"visit_date": tomorrow},
        {"visit_date": dates.today().isoformat()},
        {"result": "   "},
        {"result": "x" * 31},
    ):
        response = await api.client.post(url + "/complete", headers=headers, json=body | invalid)
        assert response.status_code == 422, response.text
    detail = await api.client.get(url, headers=headers)
    assert detail.json()["status"] == "open"

    responses = await asyncio.gather(
        api.client.post(url + "/complete", headers=headers, json=body),
        api.client.post(
            url + "/complete", headers=headers, json=body | {"result": "Follow-up requested"}
        ),
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    accepted = next(response.json() for response in responses if response.status_code == 200)
    repeated = await api.client.post(
        url + "/complete", headers=headers, json=body | {"result": "Changed"}
    )
    assert repeated.status_code == 409
    assert repeated.json()["error"]["code"] == "retention_task_not_open"
    detail = await api.client.get(url, headers=headers)
    assert detail.json() == accepted

    async with api.database.sessions() as session:
        logs = await session.scalars(
            select(AuditLog).where(
                AuditLog.entity_type == "retention_tasks",
                AuditLog.entity_id == UUID(accepted["id"]),
            )
        )
        (audit,) = logs.all()
        assert audit.action == "complete"
        assert audit.actor_id == api.users["employee"].id
        assert audit.before == {"status": "open"}
        assert audit.after["status"] == "completed"


async def test_retention_completion_rolls_back_with_audit(api, open_retention_task):
    def fail_audit_flush(session, _):
        if any(
            isinstance(row, AuditLog) and row.entity_type == "retention_tasks"
            for row in session.new
        ):
            raise DomainError(500, "test_audit_failure")

    event.listen(SyncSession, "after_flush", fail_audit_flush)
    try:
        response = await api.client.post(
            open_retention_task + "/complete",
            headers=api.headers["employee"],
            json={"visit_date": dates.format_date(dates.today()), "result": "Reached"},
        )
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "test_audit_failure"
    finally:
        event.remove(SyncSession, "after_flush", fail_audit_flush)
    detail = await api.client.get(open_retention_task, headers=api.headers["employee"])
    assert detail.json()["status"] == "open"
    assert detail.json()["completed_at"] is None
    async with api.database.sessions() as session:
        audit = await session.scalar(
            select(AuditLog.id).where(AuditLog.entity_type == "retention_tasks")
        )
        assert audit is None
