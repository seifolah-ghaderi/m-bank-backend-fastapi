from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.cli import create_supervisor
from app.main import create_app
from app.models import AuditLog, RefreshToken, User
from app.schemas.users import UserCreate


async def test_empty_database_to_all_three_roles(schema, settings, clock):
    await create_supervisor(
        schema,
        UserCreate(first_name="Ali", last_name="Test", mobile="09121234567", role="supervisor"),
        "InitialPass123",
    )
    app = create_app(settings)
    await app.state.database.close()
    app.state.database = schema
    origin = settings.cors_origins[0]

    async def login(client, mobile, password):
        response = await client.post(
            "/api/v1/auth/login", json={"mobile": mobile, "password": password}
        )
        assert response.status_code == 202, response.text
        response = await client.post(
            "/api/v1/auth/verify-sms",
            json={"challenge_id": response.json()["challenge_id"], "code": "123"},
        )
        assert response.status_code == 200, response.text
        client.headers["Authorization"] = "Bearer " + response.json()["access_token"]
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"Origin": origin}
    ) as admin:
        await login(admin, "09121234567", "InitialPass123")
        assert (await admin.get("/api/v1/cities")).status_code == 403
        response = await admin.post(
            "/api/v1/auth/change-password",
            json={"current_password": "InitialPass123", "new_password": "ChangedPass123"},
        )
        assert response.status_code == 204
        city = await admin.post("/api/v1/cities", json={"name": "تهران"})
        assert city.status_code == 201
        branches = []
        for code in ("TEH-01", "TEH-02"):
            branch = await admin.post(
                "/api/v1/branches", json={"name": code, "code": code, "city_id": city.json()["id"]}
            )
            assert branch.status_code == 201, branch.text
            branches.append(branch.json())
        for role, mobile in (("branch_manager", "09121234568"), ("employee", "09121234569")):
            created = await admin.post(
                "/api/v1/users",
                json={
                    "first_name": "New",
                    "last_name": "Staff",
                    "mobile": mobile,
                    "role": role,
                    "branch_id": branches[0]["id"],
                },
            )
            assert created.status_code == 201, created.text
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test", headers={"Origin": origin}
            ) as staff:
                await login(staff, mobile, created.json()["temporary_password"])
                assert (
                    await staff.post(
                        "/api/v1/auth/change-password",
                        json={
                            "current_password": created.json()["temporary_password"],
                            "new_password": "StaffChanged123",
                        },
                    )
                ).status_code == 204
                me = await staff.get("/api/v1/auth/me")
                assert me.json()["role"] == role
                assert me.json()["last_login_at"].startswith("1405/")
                assert (await staff.get("/api/v1/branches")).json()["total"] == 1
                assert (await staff.get(f"/api/v1/branches/{branches[1]['id']}")).status_code == 404
                csrf = await staff.get("/api/v1/auth/csrf")
                staff.headers["X-CSRF-Token"] = csrf.json()["csrf_token"]
                refreshed = await staff.post("/api/v1/auth/refresh")
                assert refreshed.status_code == 200
        audit = await admin.get("/api/v1/audit-logs")
        assert audit.status_code == 200 and audit.json()["total"] > 10
        assert all(row["occurred_at"].startswith("1405/") for row in audit.json()["items"])
    async with schema.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 3
        assert (
            await session.scalar(
                select(func.count()).select_from(AuditLog).where(AuditLog.action == "login")
            )
            == 3
        )


async def test_change_password_without_cookie_revokes_all(api):
    from tests.test_auth import full_login

    response = await full_login(api)
    api.client.cookies.clear()
    response = await api.client.post(
        "/api/v1/auth/change-password",
        headers=api.headers["supervisor"],
        json={"current_password": "ValidPass123", "new_password": "ChangedPass123"},
    )
    assert response.status_code == 204
    async with api.database.sessions() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(RefreshToken)
                .where(RefreshToken.revoked_at.is_(None))
            )
            == 0
        )


async def test_every_protected_endpoint_requires_auth_and_forced_change(api):
    admin_id = api.users["supervisor"].id
    async with api.database.sessions.begin() as session:
        admin = await session.get(User, admin_id)
        admin.must_change_password = True
    cases = [
        ("get", "/cities", None),
        ("post", "/cities", {"name": "Test"}),
        ("get", f"/cities/{api.city.id}", None),
        ("patch", f"/cities/{api.city.id}", {"name": "Test"}),
        ("delete", f"/cities/{api.city.id}", None),
        ("get", "/branches", None),
        ("post", "/branches", {}),
        ("get", f"/branches/{api.branches[0].id}", None),
        ("patch", f"/branches/{api.branches[0].id}", {}),
        ("delete", f"/branches/{api.branches[0].id}", None),
        ("get", "/users", None),
        ("post", "/users", {}),
        ("get", f"/users/{admin_id}", None),
        ("patch", f"/users/{admin_id}", {}),
        ("delete", f"/users/{admin_id}", None),
        ("post", f"/users/{admin_id}/activate", None),
        ("post", f"/users/{admin_id}/deactivate", None),
        ("post", f"/users/{admin_id}/reset-password", None),
        ("get", "/audit-logs", None),
    ]
    for method, path, body in cases:
        unauth = await api.client.request(method, "/api/v1" + path, json=body)
        assert unauth.status_code == 401, (path, unauth.text)
        forced = await api.client.request(
            method, "/api/v1" + path, json=body, headers=api.headers["supervisor"]
        )
        assert forced.status_code == 403, (path, forced.text)
        assert forced.json()["error"]["code"] == "password_change_required"
