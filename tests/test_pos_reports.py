from app.core.security import access_token
from tests.test_pos_registry import create_terminal
from tests.test_pos_transactions import add_summary
from tests.test_pos_visits import assign, dispatch


def renew_tokens(api):
    for role, user in api.users.items():
        api.headers[role] = {"Authorization": "Bearer " + access_token(api.settings, user)}


async def test_summary_scope_windows_and_pending_counts(api):
    terminals = [await create_terminal(api, device_number=f"REPORT-{i}") for i in range(3)]
    other = await create_terminal(
        api, device_number="REPORT-OTHER", branch_id=str(api.branches[1].id)
    )
    await add_summary(api, terminals[0], 0, 0)
    results = (await dispatch(api, [*terminals, other])).json()
    first, second = results[0]["visit_id"], results[1]["visit_id"]
    await assign(api, first)
    await api.client.post(
        "/api/v1/pos/visits/" + first + "/complete",
        json={"result": "visited", "tag_codes": ["maintenance_required"]},
        headers=api.headers["employee"],
    )
    await api.client.post(
        "/api/v1/pos/visits/" + second + "/assign",
        json={"assigned_to": str(api.users["employee"].id), "due_date": "1405/08/25"},
        headers=api.headers["manager"],
    )
    api.clock.advance(days=1)
    renew_tokens(api)
    url = "/api/v1/pos/reports/summary"
    response = await api.client.get(url, headers=api.headers["manager"])
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["devices_by_status"]["active"] == 3
    assert (
        report["pending_assignment"],
        report["assigned"],
        report["overdue"],
        report["completed_in_30_days"],
    ) == (1, 1, 1, 1)
    assert report["visits_by_result"] == {"visited": 1} and report["tag_counts"] == {
        "maintenance_required": 1
    }
    assert report["devices_no_transactions_in_last_3_months"] == 2
    assert (
        report["transaction_recency_from"] == "1405/05/01"
        and report["transaction_recency_to"] == "1405/07/30"
    )
    employee = (await api.client.get(url, headers=api.headers["employee"])).json()
    assert (
        employee["assigned"] == 1
        and employee["overdue"] == 1
        and employee["completed_in_30_days"] == 1
    )
    assert "devices_by_status" not in employee and "pending_assignment" not in employee
    supervisor = (await api.client.get(url, headers=api.headers["supervisor"])).json()
    assert supervisor["devices_per_branch"] == {
        str(api.branches[0].id): 3,
        str(api.branches[1].id): 1,
    }
    response = await api.client.get(
        url, params={"branch_id": str(api.branches[1].id)}, headers=api.headers["manager"]
    )
    assert response.status_code == 403
    api.clock.advance(days=31)
    renew_tokens(api)
    report = (await api.client.get(url, headers=api.headers["manager"])).json()
    assert report["completed_in_30_days"] == 0 and report["tag_counts"] == {}
