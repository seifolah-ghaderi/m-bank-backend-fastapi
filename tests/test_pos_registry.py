import asyncio

from sqlalchemy import func, select

from app.models import AuditLog, PosBranchHistory, PosDevice, PosOwnerHistory


async def create_terminal(api, **overrides):
    body = {
        "device_number": "POS-001",
        "owner_name": "Synthetic Owner",
        "address": "Synthetic store address",
        "branch_id": str(api.branches[0].id),
        "owner_mobile": "+9809173094912",
        "account_number": "00123456",
    } | overrides
    response = await api.client.post(
        "/api/v1/pos/devices", json=body, headers=api.headers["supervisor"]
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_registry_roles_normalization_and_soft_delete(api):
    device = await create_terminal(api, device_number=" ۰۰۱۲۳abc ")
    assert device["device_number"] == "00123ABC"
    assert device["owner_mobile"] == "09173094912" and device["account_number"] == "00123456"
    path = "/api/v1/pos/devices/" + device["id"]
    assert (await api.client.get(path, headers=api.headers["manager"])).status_code == 200
    for role in ("employee", "other"):
        assert (await api.client.get(path, headers=api.headers[role])).status_code == 403
    assert (
        await api.client.post("/api/v1/pos/devices", json={}, headers=api.headers["manager"])
    ).status_code in (403, 422)
    page = (
        await api.client.get(
            "/api/v1/pos/devices",
            params={"q": "00123", "page_size": 1},
            headers=api.headers["manager"],
        )
    ).json()
    assert page["total"] == 1 and page["items"][0]["id"] == device["id"]
    foreign = await create_terminal(
        api, device_number="POS-OTHER", branch_id=str(api.branches[1].id)
    )
    assert (
        await api.client.get("/api/v1/pos/devices/" + foreign["id"], headers=api.headers["manager"])
    ).status_code == 404
    assert (
        await api.client.get(
            "/api/v1/pos/devices",
            params={"branch_id": str(api.branches[1].id)},
            headers=api.headers["manager"],
        )
    ).status_code == 403
    assert (await api.client.delete(path, headers=api.headers["supervisor"])).status_code == 204
    assert (await api.client.get(path, headers=api.headers["supervisor"])).status_code == 404
    assert (
        await api.client.post(path + "/restore", headers=api.headers["supervisor"])
    ).status_code == 200
    assert (
        await api.client.patch(path, json={"owner_name": None}, headers=api.headers["supervisor"])
    ).status_code == 422


async def test_history_same_day_correction_later_transfer_and_restore_conflict(api):
    device = await create_terminal(api, effective_date="1405/07/01")
    path = "/api/v1/pos/devices/" + device["id"]
    response = await api.client.post(
        path + "/change-owner",
        json={"owner_name": "Second Owner", "effective_date": "1405/07/01"},
        headers=api.headers["supervisor"],
    )
    assert response.status_code == 200, response.text
    response = await api.client.post(
        path + "/transfer",
        json={"to_branch_id": str(api.branches[1].id), "effective_date": "1405/08/01"},
        headers=api.headers["supervisor"],
    )
    assert response.status_code == 200, response.text
    history = (
        await api.client.get(path + "/branch-history", headers=api.headers["supervisor"])
    ).json()
    assert history["total"] == 2
    assert history["items"][1]["to_date"] == "1405/07/30"
    assert (await api.client.get(path, headers=api.headers["manager"])).status_code == 404
    owners = (
        await api.client.get(path + "/owner-history", headers=api.headers["supervisor"])
    ).json()
    assert owners["total"] == 1 and owners["items"][0]["owner_name"] == "Second Owner"
    assert (await api.client.delete(path, headers=api.headers["supervisor"])).status_code == 204
    await create_terminal(api)
    conflict = await api.client.post(path + "/restore", headers=api.headers["supervisor"])
    assert conflict.status_code == 409
    async with api.database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(PosOwnerHistory)) == 2
        assert await session.scalar(select(func.count()).select_from(PosBranchHistory)) == 3
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "correct_history")
            )
            == 1
        )


async def test_concurrent_terminal_uniqueness(api):
    body = {
        "device_number": "SAME-001",
        "owner_name": "Synthetic Owner",
        "address": "Synthetic address",
        "branch_id": str(api.branches[0].id),
    }
    responses = await asyncio.gather(
        *[
            api.client.post("/api/v1/pos/devices", json=body, headers=api.headers["supervisor"])
            for _ in range(2)
        ]
    )
    assert sorted(r.status_code for r in responses) == [201, 409]
    async with api.database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(PosDevice)) == 1


async def test_device_count_and_branch_delete_guard(api):
    response = await api.client.post(
        "/api/v1/branches",
        json={"city_id": str(api.city.id), "name": "Empty Branch", "code": "007100"},
        headers=api.headers["supervisor"],
    )
    assert response.status_code == 201
    branch = response.json()
    await create_terminal(api, branch_id=branch["id"], status="retired")
    response = await api.client.get(
        "/api/v1/branches/" + branch["id"], headers=api.headers["supervisor"]
    )
    assert response.json()["pos_device_count"] == 1
    response = await api.client.delete(
        "/api/v1/branches/" + branch["id"], headers=api.headers["supervisor"]
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "branch_in_use"
    await api.client.patch(
        "/api/v1/branches/" + branch["id"],
        json={"is_active": False},
        headers=api.headers["supervisor"],
    )
    response = await api.client.post(
        "/api/v1/pos/devices",
        json={
            "device_number": "NEW-002",
            "owner_name": "Synthetic Owner",
            "address": "Synthetic address",
            "branch_id": branch["id"],
        },
        headers=api.headers["supervisor"],
    )
    assert response.status_code == 422


async def test_branch_delete_vs_terminal_create(api):
    response = await api.client.post(
        "/api/v1/branches",
        json={"city_id": str(api.city.id), "name": "Race Branch", "code": "RACE-01"},
        headers=api.headers["supervisor"],
    )
    branch = response.json()
    create, delete = await asyncio.gather(
        api.client.post(
            "/api/v1/pos/devices",
            json={
                "device_number": "RACE-001",
                "owner_name": "Synthetic Owner",
                "address": "Synthetic address",
                "branch_id": branch["id"],
            },
            headers=api.headers["supervisor"],
        ),
        api.client.delete("/api/v1/branches/" + branch["id"], headers=api.headers["supervisor"]),
    )
    assert (create.status_code, delete.status_code) in ((201, 409), (422, 204))


async def test_export_scope_safe_text_and_identifier_preservation(api):
    from io import BytesIO

    from openpyxl import load_workbook

    await create_terminal(api, device_number="000123", owner_name="=SYNTHETIC()")
    await create_terminal(api, device_number="FOREIGN-001", branch_id=str(api.branches[1].id))
    response = await api.client.get("/api/v1/pos/devices/export", headers=api.headers["manager"])
    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content))
    rows = list(workbook.active.rows)
    assert len(rows) == 2
    assert rows[1][0].value == "000123" and rows[1][0].data_type == "s"
    assert rows[1][2].value == "'=SYNTHETIC()" and rows[1][2].data_type == "s"
    assert rows[1][6].value == "00123456"
    assert (
        await api.client.get("/api/v1/pos/devices/export", headers=api.headers["employee"])
    ).status_code == 403


async def test_export_limit(api):
    from sqlalchemy import insert

    async with api.database.sessions.begin() as session:
        await session.execute(
            insert(PosDevice),
            [
                {
                    "device_number": f"LIMIT-{i}",
                    "owner_name": "Synthetic Owner",
                    "address": "Synthetic address",
                    "branch_id": api.branches[0].id,
                }
                for i in range(50001)
            ],
        )
    response = await api.client.get("/api/v1/pos/devices/export", headers=api.headers["supervisor"])
    assert response.status_code == 422 and response.json()["error"]["code"] == "too_many_rows"
