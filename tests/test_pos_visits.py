import asyncio
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.core.security import hasher
from app.models import AuditLog, Notification, PosVisit, PosVisitTagLink, User
from tests.test_pos_registry import create_terminal
from tests.test_pos_transactions import add_summary


async def dispatch(api, devices, role="supervisor", **extra):
    return await api.client.post(
        "/api/v1/pos/visits/dispatch",
        json={"pos_device_ids": [d["id"] for d in devices], "jalali_year": 1405, "jalali_month": 7}
        | extra,
        headers=api.headers[role],
    )


async def assign(api, visit_id, employee=None, role="manager"):
    return await api.client.post(
        f"/api/v1/pos/visits/{visit_id}/assign",
        json={"assigned_to": str(employee or api.users["employee"].id)},
        headers=api.headers[role],
    )


async def test_dispatch_branch_queue_assignment_and_evidence(api):
    device = await create_terminal(api)
    await add_summary(api, device, 100000000, 5)
    missing = await create_terminal(
        api, device_number="NO-DATA-001", branch_id=str(api.branches[1].id)
    )
    response = await dispatch(api, [device, missing])
    assert response.status_code == 200, response.text
    results = response.json()
    assert all(r["status"] == "created" for r in results)
    no_data = (
        await api.client.get(
            "/api/v1/pos/visits/" + results[1]["visit_id"], headers=api.headers["supervisor"]
        )
    ).json()["selection_snapshot"]
    assert no_data["no_data"] and no_data["amount"] is None and no_data["performance"] is None
    visit_id = results[0]["visit_id"]
    response = await api.client.get("/api/v1/pos/visits", headers=api.headers["manager"])
    assert (
        response.json()["total"] == 1
        and response.json()["items"][0]["status"] == "pending_assignment"
    )
    snap = response.json()["items"][0]["selection_snapshot"]
    assert (
        snap["amount"] == "100000000.00" and snap["count"] == "5" and snap["performance"] == "low"
    )
    assert (await api.client.get("/api/v1/pos/visits", headers=api.headers["employee"])).json()[
        "total"
    ] == 0
    assert (await assign(api, visit_id, role="supervisor")).status_code == 403
    assert (await dispatch(api, [device], role="manager")).status_code == 403
    assert (
        await api.client.post(
            "/api/v1/pos/visits",
            json={"pos_device_id": device["id"]},
            headers=api.headers["manager"],
        )
    ).status_code == 403
    assert (
        await api.client.get(
            "/api/v1/pos/visits/" + results[1]["visit_id"], headers=api.headers["manager"]
        )
    ).status_code == 404
    assert (await assign(api, visit_id, api.users["other"].id)).status_code == 422
    response = await assign(api, visit_id)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "assigned" and response.json()["selection_snapshot"] == snap
    await api.client.patch(
        "/api/v1/pos/performance-settings",
        json={"lower_threshold": "1", "upper_threshold": "2"},
        headers=api.headers["supervisor"],
    )
    response = await api.client.get(
        "/api/v1/pos/visits/" + visit_id, headers=api.headers["employee"]
    )
    assert (
        response.json()["selection_snapshot"] == snap
        and response.json()["device"]["device_number"] == device["device_number"]
    )
    response = await dispatch(api, [device], selection_snapshot={"amount": "0"})
    assert response.status_code == 422


async def test_completion_tags_archive_correction_and_notifications(api):
    device = await create_terminal(api)
    visit_id = (await dispatch(api, [device])).json()[0]["visit_id"]
    assert (await assign(api, visit_id)).status_code == 200
    path = "/api/v1/pos/visits/" + visit_id
    body = {
        "result": "visited",
        "tag_codes": ["maintenance_required"],
        "description": "Synthetic result",
    }
    assert (
        await api.client.post(path + "/complete", json=body, headers=api.headers["other"])
    ).status_code == 404
    response = await api.client.post(path + "/complete", json=body, headers=api.headers["employee"])
    assert response.status_code == 200, response.text
    snap = response.json()["selection_snapshot"]
    assert response.json()["status"] == "completed" and response.json()["tag_codes"] == [
        "maintenance_required"
    ]
    assert (
        await api.client.post(path + "/complete", json=body, headers=api.headers["employee"])
    ).status_code == 409
    response = await api.client.patch(
        path,
        json={"result": "shop_closed", "tag_codes": [], "description": "Corrected"},
        headers=api.headers["supervisor"],
    )
    assert response.status_code == 200 and response.json()["tag_codes"] == []
    assert response.json()["selection_snapshot"] == snap
    archived = (
        await api.client.get(
            "/api/v1/pos/visits", params={"archived": True}, headers=api.headers["employee"]
        )
    ).json()
    assert archived["total"] == 1
    device_detail = (
        await api.client.get(
            "/api/v1/pos/devices/" + device["id"], headers=api.headers["supervisor"]
        )
    ).json()
    assert device_detail["status"] == "active" and device_detail["open_visit"] is None
    async with api.database.sessions() as session:
        link = await session.scalar(select(PosVisitTagLink))
        assert link.is_active is False
        events = list(await session.scalars(select(Notification.event_type)))
        assert sorted(events) == [
            "pos_visit_assigned",
            "pos_visit_completed",
            "pos_visit_dispatched",
        ]
        audit = await session.scalar(select(AuditLog).where(AuditLog.action == "correct_visit"))
        assert (
            audit.before["tag_codes"] == ["maintenance_required"] and audit.after["tag_codes"] == []
        )


async def test_transfer_cancels_both_open_states_and_preserves_branch(api):
    pending = await create_terminal(api, device_number="PENDING-001")
    assigned = await create_terminal(api, device_number="ASSIGNED-001")
    results = (await dispatch(api, [pending, assigned])).json()
    await assign(api, results[1]["visit_id"])
    for device, result in zip([pending, assigned], results, strict=True):
        detail = (
            await api.client.get(
                "/api/v1/pos/visits/" + result["visit_id"], headers=api.headers["manager"]
            )
        ).json()
        response = await api.client.post(
            "/api/v1/pos/devices/" + device["id"] + "/transfer",
            json={"to_branch_id": str(api.branches[1].id)},
            headers=api.headers["supervisor"],
        )
        assert response.status_code == 200, response.text
        final = (
            await api.client.get(
                "/api/v1/pos/visits/" + result["visit_id"], headers=api.headers["manager"]
            )
        ).json()
        assert final["status"] == "cancelled" and final["cancel_reason"] == "device_transferred"
        assert (
            final["branch_id"] == str(api.branches[0].id)
            and final["selection_snapshot"] == detail["selection_snapshot"]
        )


async def test_employee_lifecycle_guard_and_reassignment(api):
    device = await create_terminal(api)
    visit_id = (await dispatch(api, [device])).json()[0]["visit_id"]
    await assign(api, visit_id)
    for action, body in (
        ("/deactivate", None),
        ("", {"role": "branch_manager"}),
        ("", {"branch_id": str(api.branches[1].id)}),
    ):
        path = "/api/v1/users/" + str(api.users["employee"].id) + action
        response = await (
            api.client.post(path, headers=api.headers["supervisor"])
            if action
            else api.client.patch(path, json=body, headers=api.headers["supervisor"])
        )
        assert (
            response.status_code == 409
            and response.json()["error"]["code"] == "user_has_open_tasks"
        )
    response = await api.client.delete(
        "/api/v1/users/" + str(api.users["employee"].id), headers=api.headers["supervisor"]
    )
    assert response.status_code == 409
    async with api.database.sessions.begin() as session:
        new = User(
            first_name="New",
            last_name="Employee",
            mobile="09123456777",
            password_hash=hasher.hash("ValidPass123"),
            role="employee",
            branch_id=api.branches[0].id,
            must_change_password=False,
        )
        session.add(new)
    response = await api.client.post(
        "/api/v1/pos/visits/" + visit_id + "/reassign",
        json={"assigned_to": str(new.id)},
        headers=api.headers["manager"],
    )
    assert response.status_code == 200, response.text
    assert (
        await api.client.get("/api/v1/pos/visits/" + visit_id, headers=api.headers["employee"])
    ).status_code == 404
    old = (await api.client.get("/api/v1/notifications", headers=api.headers["employee"])).json()[
        "items"
    ]
    assert old
    assert (
        await api.client.get(
            "/api/v1/notifications/" + old[0]["id"], headers=api.headers["employee"]
        )
    ).status_code == 200
    assert (
        await api.client.post(
            "/api/v1/users/" + str(api.users["employee"].id) + "/deactivate",
            headers=api.headers["supervisor"],
        )
    ).status_code == 200


async def test_bulk_dispatch_partial_results_and_bulk_assignment(api):
    good = await create_terminal(api)
    retired = await create_terminal(api, device_number="RETIRED-001", status="retired")
    results = (await dispatch(api, [good, retired, good])).json()
    assert [r["status"] for r in results] == ["created", "error", "error"]
    response = await api.client.post(
        "/api/v1/pos/visits/bulk-assign",
        json={
            "visit_ids": [results[0]["visit_id"], str(UUID(int=1))],
            "assigned_to": str(api.users["employee"].id),
        },
        headers=api.headers["manager"],
    )
    assert response.status_code == 200, response.text
    assert [r["status"] for r in response.json()] == ["assigned", "error"]


async def test_notifications_privacy_idempotence_and_rollback(api):
    from types import SimpleNamespace

    from app.core.db import transaction
    from app.core.notifications import notify

    visit = SimpleNamespace(id=UUID(int=1), pos_device_id=UUID(int=2))
    with pytest.raises(ValueError):
        async with transaction(api.database) as session:
            notify(session, api.users["employee"].id, "pos_visit_assigned", visit)
            await session.flush()
            raise ValueError("rollback")
    assert (
        await api.client.get("/api/v1/notifications/unread-count", headers=api.headers["employee"])
    ).json()["count"] == 0
    async with api.database.sessions.begin() as session:
        notify(session, api.users["employee"].id, "pos_visit_assigned", visit)
    rows = (await api.client.get("/api/v1/notifications", headers=api.headers["employee"])).json()[
        "items"
    ]
    path = "/api/v1/notifications/" + rows[0]["id"]
    assert (await api.client.get(path, headers=api.headers["other"])).status_code == 404
    assert (await api.client.post(path + "/read", headers=api.headers["other"])).status_code == 404
    assert (
        await api.client.post(path + "/read", headers=api.headers["employee"])
    ).status_code == 204
    first = (await api.client.get(path, headers=api.headers["employee"])).json()["read_at"]
    api.clock.advance(minutes=5)
    await api.client.post(path + "/read", headers=api.headers["employee"])
    assert (await api.client.get(path, headers=api.headers["employee"])).json()["read_at"] == first
    assert (
        await api.client.post("/api/v1/notifications/read-all", headers=api.headers["employee"])
    ).status_code == 204


async def test_concurrent_dispatch_and_completion_vs_transfer(api):
    device = await create_terminal(api)
    responses = await asyncio.gather(dispatch(api, [device]), dispatch(api, [device]))
    results = [r.json()[0] for r in responses]
    assert sorted(r["status"] for r in results) == ["created", "error"]
    visit_id = next(r["visit_id"] for r in results if r["status"] == "created")
    await assign(api, visit_id)
    completed, transferred = await asyncio.gather(
        api.client.post(
            "/api/v1/pos/visits/" + visit_id + "/complete",
            json={"result": "visited"},
            headers=api.headers["employee"],
        ),
        api.client.post(
            "/api/v1/pos/devices/" + device["id"] + "/transfer",
            json={"to_branch_id": str(api.branches[1].id)},
            headers=api.headers["supervisor"],
        ),
    )
    assert transferred.status_code == 200
    assert completed.status_code in (200, 409)
    async with api.database.sessions() as session:
        visit = await session.get(PosVisit, UUID(visit_id))
        assert visit.status == ("completed" if completed.status_code == 200 else "cancelled")
        assert visit.branch_id == api.branches[0].id
        count = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.entity_id == visit.id, AuditLog.action == "complete")
        )
        assert count == (1 if completed.status_code == 200 else 0)


@pytest.mark.parametrize("change", ["deactivate", "move"])
async def test_assignment_vs_employee_lifecycle(api, change):
    device = await create_terminal(api)
    visit_id = (await dispatch(api, [device])).json()[0]["visit_id"]
    user_path = "/api/v1/users/" + str(api.users["employee"].id)
    operation = (
        api.client.post(user_path + "/deactivate", headers=api.headers["supervisor"])
        if change == "deactivate"
        else api.client.patch(
            user_path,
            json={"branch_id": str(api.branches[1].id)},
            headers=api.headers["supervisor"],
        )
    )
    assigned, changed = await asyncio.gather(assign(api, visit_id), operation)
    assert (assigned.status_code, changed.status_code) in ((200, 409), (422, 200))
    async with api.database.sessions() as session:
        user = await session.get(User, api.users["employee"].id)
        visit = await session.get(PosVisit, UUID(visit_id))
        if visit.status == "assigned":
            assert user.is_active and user.branch_id == visit.branch_id


async def test_cancel_vs_completion_and_archived_user_move(api):
    device = await create_terminal(api)
    visit_id = (await dispatch(api, [device])).json()[0]["visit_id"]
    await assign(api, visit_id)
    path = "/api/v1/pos/visits/" + visit_id
    complete, cancel = await asyncio.gather(
        api.client.post(
            path + "/complete", json={"result": "visited"}, headers=api.headers["employee"]
        ),
        api.client.post(
            path + "/cancel",
            json={"cancel_reason": "Synthetic cancellation"},
            headers=api.headers["manager"],
        ),
    )
    assert sorted([complete.status_code, cancel.status_code]) == [200, 409]
    response = await api.client.patch(
        "/api/v1/users/" + str(api.users["employee"].id),
        json={"branch_id": str(api.branches[1].id)},
        headers=api.headers["supervisor"],
    )
    assert response.status_code == 200, response.text
    assert (await api.client.get(path, headers=api.headers["employee"])).status_code == 200


async def test_visit_validation_tags_and_inactive_branch(api):
    device = await create_terminal(api)
    visit_id = (await dispatch(api, [device])).json()[0]["visit_id"]
    response = await api.client.post(
        "/api/v1/pos/visits/" + visit_id + "/assign",
        json={"assigned_to": str(api.users["employee"].id), "due_date": "1405/07/01"},
        headers=api.headers["manager"],
    )
    assert response.status_code == 422
    await assign(api, visit_id)
    path = "/api/v1/pos/visits/" + visit_id
    for extra in (
        {"tag_codes": ["broken_device", "broken_device"]},
        {"visited_at": "1405/09/01T12:00:00+03:30"},
        {"visited_at": "1405/07/01T12:00:00+03:30"},
    ):
        response = await api.client.post(
            path + "/complete", json={"result": "visited"} | extra, headers=api.headers["employee"]
        )
        assert response.status_code == 422, response.text
    tags = (await api.client.get("/api/v1/pos/tags", headers=api.headers["employee"])).json()[
        "items"
    ]
    broken = next(t for t in tags if t["code"] == "broken_device")
    await api.client.patch(
        "/api/v1/pos/tags/" + broken["id"],
        json={"is_active": False},
        headers=api.headers["supervisor"],
    )
    response = await api.client.post(
        path + "/complete",
        json={"result": "visited", "tag_codes": ["broken_device"]},
        headers=api.headers["employee"],
    )
    assert response.status_code == 422
    await api.client.patch(
        "/api/v1/branches/" + str(api.branches[0].id),
        json={"is_active": False},
        headers=api.headers["supervisor"],
    )
    response = await api.client.post(
        path + "/complete", json={"result": "visited"}, headers=api.headers["employee"]
    )
    assert response.status_code == 200, response.text
