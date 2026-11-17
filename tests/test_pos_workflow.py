from decimal import Decimal

from sqlalchemy import select

from app.models import AuditLog
from tests.test_pos_imports import ACTIVITY, REGISTRY, xlsx
from tests.test_pos_visits import assign, dispatch


async def test_import_to_visit_then_correct_without_rewriting_evidence(api, tmp_path):
    api.settings.import_storage_dir = tmp_path

    async def upload(kind, headers, rows):
        response = await api.client.post(
            "/api/v1/pos/imports/" + kind,
            files={"file": ("synthetic.xlsx", xlsx(headers, rows))},
            data={"jalali_year": 1405, "jalali_month": 7},
            headers=api.headers["supervisor"],
        )
        assert response.status_code == 200, response.text
        return response.json()

    created = await upload(
        "devices",
        REGISTRY,
        [
            [
                "WORKFLOW-001",
                api.branches[0].code,
                "Synthetic Owner",
                "Synthetic address",
                "9173094912",
            ]
        ],
    )
    assert created["created"] == 1
    await upload("transactions", ACTIVITY, [["WORKFLOW-001", 100000000, 10]])
    device = (
        await api.client.get("/api/v1/pos/devices", headers=api.headers["supervisor"])
    ).json()["items"][0]
    url = "/api/v1/pos/devices/" + device["id"] + "/productivity"
    assert (await api.client.get(url, headers=api.headers["supervisor"])).json()[
        "performance"
    ] == "low"
    visit_id = (await dispatch(api, [device])).json()[0]["visit_id"]
    assigned = await assign(api, visit_id)
    assert assigned.status_code == 200
    original = assigned.json()["selection_snapshot"]
    response = await api.client.post(
        "/api/v1/pos/visits/" + visit_id + "/complete",
        json={
            "result": "visited",
            "tag_codes": ["maintenance_required"],
            "description": "Synthetic follow-up",
        },
        headers=api.headers["employee"],
    )
    assert response.status_code == 200
    correction = await upload("transactions", ACTIVITY, [["WORKFLOW-001", 1500000000, 20]])
    assert correction["updated"] == 1
    assert (await api.client.get(url, headers=api.headers["supervisor"])).json()[
        "performance"
    ] == "high"
    await api.client.patch(
        "/api/v1/pos/performance-settings",
        json={"lower_threshold": "2000000000", "upper_threshold": "3000000000"},
        headers=api.headers["supervisor"],
    )
    live = (await api.client.get(url, headers=api.headers["supervisor"])).json()
    assert live["performance"] == "low" and live["transaction_count"] == "20"
    saved = (
        await api.client.get("/api/v1/pos/visits/" + visit_id, headers=api.headers["employee"])
    ).json()
    assert saved["selection_snapshot"] == original
    assert (
        original["amount"] == "100000000.00"
        and original["count"] == "10"
        and original["policy_version"] == 1
    )
    report = (
        await api.client.get("/api/v1/pos/reports/summary", headers=api.headers["employee"])
    ).json()
    assert report["completed_in_30_days"] == 1
    async with api.database.sessions() as session:
        audit = await session.scalar(
            select(AuditLog).where(
                AuditLog.entity_type == "pos_monthly_transactions", AuditLog.action == "update"
            )
        )
        assert Decimal(audit.before["transaction_amount"]) == Decimal("100000000.00")
        assert Decimal(audit.after["transaction_amount"]) == Decimal("1500000000.00")
