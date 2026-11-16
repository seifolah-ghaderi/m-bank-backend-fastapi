import asyncio

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, City, User


async def test_city_crud_normalized_uniqueness_and_history(api):
    headers = api.headers["supervisor"]
    first = await api.client.post("/api/v1/cities", headers=headers, json={"name": "  كرج "})
    assert first.status_code == 201, first.text
    city = first.json()
    assert city["name"] == "کرج"
    assert city["created_at"].startswith("1405/")
    assert (
        await api.client.post("/api/v1/cities", headers=headers, json={"name": "کرج"})
    ).status_code == 409
    response = await api.client.patch(
        f"/api/v1/cities/{city['id']}", headers=headers, json={"is_active": False}
    )
    assert response.status_code == 200
    lookup = await api.client.get("/api/v1/cities?include_inactive=false", headers=headers)
    assert city["id"] not in [r["id"] for r in lookup.json()["items"]]
    assert (
        await api.client.delete(f"/api/v1/cities/{city['id']}", headers=headers)
    ).status_code == 204
    assert (
        await api.client.get(f"/api/v1/cities/{city['id']}", headers=headers)
    ).status_code == 404
    assert (
        await api.client.post("/api/v1/cities", headers=headers, json={"name": "کرج"})
    ).status_code == 201
    async with api.database.sessions() as session:
        old = await session.get(City, city["id"])
        assert old.deleted_at is not None
        assert old.deleted_by == api.users["supervisor"].id


async def test_org_dependency_guards_and_branch_move(api):
    headers = api.headers["supervisor"]
    response = await api.client.delete(f"/api/v1/cities/{api.city.id}", headers=headers)
    assert response.status_code == 409 and response.json()["error"]["code"] == "city_has_branches"
    response = await api.client.delete(f"/api/v1/branches/{api.branches[0].id}", headers=headers)
    assert response.status_code == 409 and response.json()["error"]["code"] == "branch_in_use"
    new_city = (
        await api.client.post("/api/v1/cities", headers=headers, json={"name": "Shiraz"})
    ).json()
    response = await api.client.patch(
        f"/api/v1/branches/{api.branches[0].id}", headers=headers, json={"city_id": new_city["id"]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["manager"]["id"] == str(api.users["manager"].id)
    assert response.json()["active_employee_count"] == 1
    assert (await api.client.get("/api/v1/auth/me", headers=api.headers["employee"])).json()[
        "city"
    ]["id"] == new_city["id"]


async def test_branch_scoping_and_pagination(api):
    for key in ("manager", "employee"):
        headers = api.headers[key]
        response = await api.client.get("/api/v1/branches", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["total"] == 1
        assert response.json()["items"][0]["id"] == str(api.branches[0].id)
        assert (
            await api.client.get(f"/api/v1/branches/{api.branches[1].id}", headers=headers)
        ).status_code == 404
    assert (
        await api.client.get(
            f"/api/v1/branches?branch_id={api.branches[1].id}", headers=api.headers["manager"]
        )
    ).status_code == 403
    for query in ("page=0", "page_size=101", "sort=password_hash"):
        assert (
            await api.client.get(f"/api/v1/branches?{query}", headers=api.headers["supervisor"])
        ).status_code == 422


async def test_user_lifecycle_and_identity_reuse(api):
    headers = api.headers["supervisor"]
    body = {
        "first_name": "Sara",
        "last_name": "Test",
        "mobile": "+98 912 345 6799",
        "role": "employee",
        "branch_id": str(api.branches[0].id),
    }
    response = await api.client.post("/api/v1/users", headers=headers, json=body)
    assert response.status_code == 201, response.text
    user = response.json()
    assert len(user["temporary_password"]) == 10 and user["must_change_password"]
    detail = await api.client.get(f"/api/v1/users/{user['id']}", headers=headers)
    assert "temporary_password" not in detail.text and "password_hash" not in detail.text
    assert (await api.client.post("/api/v1/users", headers=headers, json=body)).status_code == 409
    assert (
        await api.client.delete(f"/api/v1/users/{user['id']}", headers=headers)
    ).status_code == 204
    assert (await api.client.post("/api/v1/users", headers=headers, json=body)).status_code == 201


async def test_staff_scoping_and_current_role(api):
    manager = api.headers["manager"]
    response = await api.client.get("/api/v1/users", headers=manager)
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 2
    assert (
        await api.client.get(f"/api/v1/users/{api.users['other'].id}", headers=manager)
    ).status_code == 404
    assert (
        await api.client.get("/api/v1/users", headers=api.headers["employee"])
    ).status_code == 403
    target = api.users["manager"]
    async with api.database.sessions.begin() as session:
        user = await session.get(User, target.id)
        user.role = "employee"
        user.branch_id = api.branches[1].id
    assert (await api.client.get("/api/v1/users", headers=manager)).status_code == 403
    assert (await api.client.get("/api/v1/branches", headers=manager)).json()["items"][0][
        "id"
    ] == str(api.branches[1].id)
    async with api.database.sessions.begin() as session:
        user = await session.get(User, target.id)
        user.is_active = False
    assert (await api.client.get("/api/v1/auth/me", headers=manager)).status_code == 401


async def test_manager_conflict_inactive_branch_and_self_guards(api):
    headers = api.headers["supervisor"]
    target = api.users["employee"].id
    assert (
        await api.client.patch(
            f"/api/v1/users/{target}", headers=headers, json={"role": "branch_manager"}
        )
    ).status_code == 409
    await api.client.patch(
        f"/api/v1/branches/{api.branches[1].id}", headers=headers, json={"is_active": False}
    )
    assert (
        await api.client.patch(
            f"/api/v1/users/{target}", headers=headers, json={"branch_id": str(api.branches[1].id)}
        )
    ).status_code == 422
    supervisor = api.users["supervisor"].id
    for verb, suffix, body in (
        ("post", "/deactivate", None),
        ("delete", "", None),
        ("patch", "", {"role": "employee", "branch_id": str(api.branches[0].id)}),
    ):
        response = await api.client.request(
            verb, f"/api/v1/users/{supervisor}{suffix}", headers=headers, json=body
        )
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "cannot_modify_self"


async def test_concurrent_supervisor_removal(api):
    async def remove(actor, target):
        return await api.client.post(
            f"/api/v1/users/{api.users[target].id}/deactivate", headers=api.headers[actor]
        )

    responses = await asyncio.gather(
        remove("supervisor", "supervisor2"), remove("supervisor2", "supervisor")
    )
    assert sorted(r.status_code for r in responses) == [200, 401]
    async with api.database.sessions() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(User)
                .where(User.role == "supervisor", User.is_active.is_(True))
            )
            == 1
        )


async def test_concurrent_manager_promotions(api):
    headers = api.headers["supervisor"]

    async def promote(key):
        return await api.client.patch(
            f"/api/v1/users/{api.users[key].id}",
            headers=headers,
            json={"role": "branch_manager", "branch_id": str(api.branches[1].id)},
        )

    responses = await asyncio.gather(promote("employee"), promote("other"))
    assert sorted(r.status_code for r in responses) == [200, 409]


@pytest.mark.parametrize("key", ["manager", "employee"])
@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "/cities", {"name": "Forbidden"}),
        ("post", "/branches", {}),
        ("post", "/users", {}),
        ("patch", "/cities/{city}", {"name": "Forbidden"}),
        ("delete", "/cities/{city}", None),
        ("patch", "/branches/{branch}", {"name": "Forbidden"}),
        ("delete", "/branches/{branch}", None),
        ("patch", "/users/{user}", {"first_name": "Forbidden"}),
        ("delete", "/users/{user}", None),
        ("post", "/users/{user}/activate", None),
        ("post", "/users/{user}/deactivate", None),
        ("post", "/users/{user}/reset-password", None),
        ("get", "/audit-logs", None),
    ],
)
async def test_privileged_endpoint_matrix(api, key, method, path, body):
    path = path.format(city=api.city.id, branch=api.branches[0].id, user=api.users["other"].id)
    response = await api.client.request(
        method, "/api/v1" + path, headers=api.headers[key], json=body
    )
    assert response.status_code == 403, response.text


async def test_audit_jalali_filters_and_no_read_entries(api):
    headers = api.headers["supervisor"]
    await api.client.patch(
        f"/api/v1/cities/{api.city.id}", headers=headers, json={"is_active": False}
    )
    response = await api.client.get(
        "/api/v1/audit-logs?entity_type=cities&action=update&from_date=1405/08/25&to_date=1405/08/25",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    entry = response.json()["items"][0]
    assert entry["occurred_at"].startswith("1405/")
    assert entry["after"]["is_active"] is False
    assert (
        await api.client.get("/api/v1/audit-logs?from_date=1400/12/30", headers=headers)
    ).status_code == 422
    async with api.database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(AuditLog)) == 1
