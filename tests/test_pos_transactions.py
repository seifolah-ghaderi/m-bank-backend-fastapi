import asyncio

from sqlalchemy import select

from app.models import AuditLog
from tests.test_pos_registry import create_terminal

PERIOD = {"from_date": "1405/07/01", "to_date": "1405/07/30"}


async def add_summary(api, device, amount=0, count=0, **overrides):
    response = await api.client.post(
        f"/api/v1/pos/devices/{device['id']}/transactions",
        json=PERIOD | {"transaction_amount": str(amount), "transaction_count": count} | overrides,
        headers=api.headers["supervisor"],
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_summary_corrections_overlap_and_scope(api):
    device = await create_terminal(api, status="retired")
    summary = await add_summary(api, device, "100.01", 3)
    path = f"/api/v1/pos/devices/{device['id']}/transactions"
    assert (await api.client.get(path, headers=api.headers["manager"])).json()["total"] == 1
    assert (await api.client.get(path, headers=api.headers["employee"])).status_code == 403
    response = await api.client.patch(
        "/api/v1/pos/transactions/" + summary["id"],
        json={"transaction_count": 4},
        headers=api.headers["supervisor"],
    )
    assert response.status_code == 200 and response.json()["transaction_amount"] == "100.01"
    response = await api.client.post(
        path,
        json=PERIOD | {"transaction_amount": "1", "transaction_count": 0},
        headers=api.headers["supervisor"],
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "overlapping_period"
    response = await api.client.patch(
        "/api/v1/pos/transactions/" + summary["id"],
        json={"from_date": "1405/08/01"},
        headers=api.headers["supervisor"],
    )
    assert response.status_code == 422
    for field, value in (
        ("transaction_count", 1.5),
        ("transaction_count", -1),
        ("transaction_amount", "-1"),
    ):
        response = await api.client.post(
            path,
            json=PERIOD | {"transaction_amount": "0", "transaction_count": 0} | {field: value},
            headers=api.headers["supervisor"],
        )
        assert response.status_code == 422
    async with api.database.sessions() as session:
        audit = await session.scalar(
            select(AuditLog).where(
                AuditLog.action == "update", AuditLog.entity_type == "pos_monthly_transactions"
            )
        )
        assert audit.before["transaction_count"] == 3 and audit.after["transaction_count"] == 4
    response = await api.client.delete(
        "/api/v1/pos/transactions/" + summary["id"], headers=api.headers["supervisor"]
    )
    assert response.status_code == 204
    assert (await api.client.get(path, headers=api.headers["manager"])).json()["total"] == 0


async def test_summary_concurrency(api):
    device = await create_terminal(api)
    path = f"/api/v1/pos/devices/{device['id']}/transactions"
    responses = await asyncio.gather(
        *[
            api.client.post(
                path,
                json=PERIOD | {"transaction_amount": "5", "transaction_count": 1},
                headers=api.headers["supervisor"],
            )
            for _ in range(2)
        ]
    )
    assert sorted(r.status_code for r in responses) == [201, 409]


async def test_performance_boundaries_no_data_scope_and_policy(api):
    devices = []
    for i, amount in enumerate((0, 199999999, 200000000, 1000000000, 1000000001, None)):
        d = await create_terminal(api, device_number=f"BOUND-{i}")
        devices.append(d)
        if amount is not None:
            await add_summary(api, d, amount, 3)
    await create_terminal(api, device_number="FOREIGN-001", branch_id=str(api.branches[1].id))
    response = await api.client.get(
        "/api/v1/pos/productivity",
        params={"jalali_year": 1405, "jalali_month": 7},
        headers=api.headers["manager"],
    )
    assert response.status_code == 200, response.text
    rows = {r["device_number"]: r for r in response.json()["items"]}
    assert [rows[f"BOUND-{i}"]["performance"] for i in range(6)] == [
        "low",
        "low",
        "normal",
        "normal",
        "high",
        None,
    ]
    assert rows["BOUND-0"]["no_data"] is False and rows["BOUND-5"]["no_data"] is True
    assert rows["BOUND-5"]["transaction_amount"] is None
    assert response.json()["total"] == 6
    assert (
        await api.client.get(
            "/api/v1/pos/productivity",
            params={"branch_id": str(api.branches[1].id)},
            headers=api.headers["manager"],
        )
    ).status_code == 403
    response = await api.client.get(
        f"/api/v1/pos/devices/{devices[2]['id']}/productivity", headers=api.headers["supervisor"]
    )
    assert response.status_code == 200 and response.json()["performance"] == "normal"
    assert response.json()["series"][0]["from_date"] == "1405/07/01"
    response = await api.client.patch(
        "/api/v1/pos/performance-settings",
        json={"lower_threshold": "300000000", "upper_threshold": "2000000000"},
        headers=api.headers["manager"],
    )
    assert response.status_code == 403
    response = await api.client.patch(
        "/api/v1/pos/performance-settings",
        json={"lower_threshold": "300000000", "upper_threshold": "2000000000"},
        headers=api.headers["supervisor"],
    )
    assert response.status_code == 200 and response.json()["policy_version"] == 2
    response = await api.client.get(
        f"/api/v1/pos/devices/{devices[2]['id']}/productivity", headers=api.headers["supervisor"]
    )
    assert response.json()["performance"] == "low"
    response = await api.client.patch(
        "/api/v1/pos/performance-settings",
        json={"lower_threshold": "500", "upper_threshold": "100"},
        headers=api.headers["supervisor"],
    )
    assert response.status_code == 422


async def test_range_total_and_partial_overlap(api):
    device = await create_terminal(api)
    await add_summary(api, device, 150000000, 4)
    await add_summary(api, device, 150000000, 5, from_date="1405/08/01", to_date="1405/08/30")
    path = f"/api/v1/pos/devices/{device['id']}/productivity"
    response = await api.client.get(
        path,
        params={"from_date": "1405/07/01", "to_date": "1405/08/30"},
        headers=api.headers["supervisor"],
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert (
        data["performance"] == "normal"
        and data["transaction_amount"] == "300000000.00"
        and data["transaction_count"] == "9"
    )
    assert data["record_count"] == 2 and data["covered_days"] == 60
    response = await api.client.get(
        path,
        params={"from_date": "1405/07/15", "to_date": "1405/07/30"},
        headers=api.headers["supervisor"],
    )
    assert response.json()["no_data"] is True


async def test_exact_period_service_upsert_and_policy_atomicity(api):
    from uuid import UUID

    from app.features.pos.service_transactions import write_transaction
    from app.schemas.pos import PosTransactionCreate

    device = await create_terminal(api)
    await add_summary(api, device, 100, 2)
    async with api.database.sessions.begin() as session:
        _, result = await write_transaction(
            session,
            api.users["supervisor"],
            UUID(device["id"]),
            PosTransactionCreate(**PERIOD, transaction_amount="100", transaction_count=3),
            upsert=True,
        )
        assert result == "updated"
    async with api.database.sessions.begin() as session:
        _, result = await write_transaction(
            session,
            api.users["supervisor"],
            UUID(device["id"]),
            PosTransactionCreate(**PERIOD, transaction_amount="100", transaction_count=3),
            upsert=True,
        )
        assert result == "unchanged"
    pairs = [
        {"lower_threshold": "100", "upper_threshold": "200"},
        {"lower_threshold": "300", "upper_threshold": "400"},
    ]
    responses = await asyncio.gather(
        *[
            api.client.patch(
                "/api/v1/pos/performance-settings", json=pair, headers=api.headers[role]
            )
            for pair, role in zip(pairs, ("supervisor", "supervisor2"), strict=True)
        ]
    )
    assert all(r.status_code == 200 for r in responses)
    saved = (
        await api.client.get("/api/v1/pos/performance-settings", headers=api.headers["manager"])
    ).json()
    assert (saved["lower_threshold"], saved["upper_threshold"]) in [
        ("100.00", "200.00"),
        ("300.00", "400.00"),
    ]
    assert saved["policy_version"] == 3
