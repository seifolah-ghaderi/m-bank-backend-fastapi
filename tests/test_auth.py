import asyncio

import pytest
from sqlalchemy import func, select

from app.core.sms import SmsDeliveryError
from app.models import AuditLog, LoginChallenge, RefreshToken, User


async def first_factor(api, key="supervisor", password="ValidPass123"):
    return await api.client.post(
        "/api/v1/auth/login", json={"mobile": api.users[key].mobile, "password": password}
    )


async def full_login(api, key="supervisor"):
    first = await first_factor(api, key)
    assert first.status_code == 202, first.text
    response = await api.client.post(
        "/api/v1/auth/verify-sms",
        json={"challenge_id": first.json()["challenge_id"], "code": "123"},
    )
    assert response.status_code == 200, response.text
    return response


async def test_two_factor_and_cookie_flow(api):
    first = await first_factor(api)
    assert first.status_code == 202, first.text
    assert "access_token" not in first.text
    async with api.database.sessions() as session:
        assert (await session.get(User, api.users["supervisor"].id)).last_login_at is None
        assert await session.scalar(select(func.count()).select_from(RefreshToken)) == 0
    verified = await api.client.post(
        "/api/v1/auth/verify-sms",
        json={"challenge_id": first.json()["challenge_id"], "code": "123"},
    )
    assert verified.status_code == 200, verified.text
    assert "refresh_token" not in verified.json()
    cookie = verified.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/api/v1/auth" in cookie
    assert "Domain=" not in cookie
    assert verified.json()["user"]["last_login_at"].startswith("1405/")
    token = verified.json()["access_token"]
    me = await api.client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token})
    assert me.status_code == 200, me.text
    assert me.json()["role"] == "supervisor"
    assert (await api.client.post("/api/v1/auth/refresh")).status_code == 403
    csrf = await api.client.get("/api/v1/auth/csrf")
    assert csrf.headers["cache-control"] == "no-store"
    refreshed = await api.client.post(
        "/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf.json()["csrf_token"]}
    )
    assert refreshed.status_code == 200, refreshed.text
    assert (
        await api.client.post(
            "/api/v1/auth/verify-sms",
            json={"challenge_id": first.json()["challenge_id"], "code": "123"},
        )
    ).status_code == 401


async def test_password_lockout_persists(api):
    for _ in range(5):
        assert (await first_factor(api, password="wrong")).status_code == 401
    assert (await first_factor(api)).status_code == 423
    async with api.database.sessions() as session:
        user = await session.get(User, api.users["supervisor"].id)
        assert user.failed_login_count == 5
        assert (
            await session.scalar(
                select(func.count()).select_from(AuditLog).where(AuditLog.action == "login_failed")
            )
            == 5
        )
    api.clock.advance(minutes=16)
    assert (await first_factor(api)).status_code == 202


async def test_sms_attempts_and_expiry(api):
    first = (await first_factor(api)).json()
    for _ in range(5):
        response = await api.client.post(
            "/api/v1/auth/verify-sms", json={"challenge_id": first["challenge_id"], "code": "999"}
        )
        assert response.status_code == 401
    response = await api.client.post(
        "/api/v1/auth/verify-sms", json={"challenge_id": first["challenge_id"], "code": "123"}
    )
    assert response.status_code == 401
    api.clock.advance(seconds=61)
    first = (await first_factor(api)).json()
    api.clock.advance(minutes=5)
    response = await api.client.post(
        "/api/v1/auth/verify-sms", json={"challenge_id": first["challenge_id"], "code": "123"}
    )
    assert response.status_code == 401


async def test_resend_limits_and_replacement(api):
    first = (await first_factor(api)).json()
    assert (await first_factor(api)).status_code == 429
    assert (
        await api.client.post(
            "/api/v1/auth/resend-sms", json={"challenge_id": first["challenge_id"]}
        )
    ).status_code == 429
    await api.client.post(
        "/api/v1/auth/verify-sms", json={"challenge_id": first["challenge_id"], "code": "999"}
    )
    api.clock.advance(seconds=60)
    resent = await api.client.post(
        "/api/v1/auth/resend-sms", json={"challenge_id": first["challenge_id"]}
    )
    assert resent.status_code == 202, resent.text
    assert resent.json()["challenge_id"] != first["challenge_id"]
    assert resent.json()["expires_in"] == 240
    assert (
        await api.client.post(
            "/api/v1/auth/verify-sms", json={"challenge_id": first["challenge_id"], "code": "123"}
        )
    ).status_code == 401
    async with api.database.sessions() as session:
        latest = await session.scalar(
            select(LoginChallenge).where(LoginChallenge.invalidated_at.is_(None))
        )
        assert latest.failed_attempts == 1


async def test_sms_failure_never_authenticates(api):
    async def fail(*args):
        raise SmsDeliveryError()

    api.app.state.sms.send = fail
    response = await first_factor(api)
    assert response.status_code == 503
    async with api.database.sessions() as session:
        challenge = await session.scalar(select(LoginChallenge))
        assert challenge.delivery_state == "failed"
        challenge_id = str(challenge.id)
    assert (
        await api.client.post(
            "/api/v1/auth/verify-sms", json={"challenge_id": challenge_id, "code": "123"}
        )
    ).status_code == 401


async def test_concurrent_sms_verification(api):
    first = (await first_factor(api)).json()

    async def verify():
        return await api.client.post(
            "/api/v1/auth/verify-sms", json={"challenge_id": first["challenge_id"], "code": "123"}
        )

    responses = await asyncio.gather(verify(), verify())
    assert sorted(r.status_code for r in responses) == [200, 401]
    async with api.database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(RefreshToken)) == 1


async def test_refresh_reuse_revokes_all_sessions(api):
    login = await full_login(api)
    raw = api.client.cookies.get("crm_refresh")
    csrf = login.json()["csrf_token"]
    response = await api.client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200
    response = await api.client.post(
        "/api/v1/auth/refresh", headers={"Cookie": f"crm_refresh={raw}", "X-CSRF-Token": csrf}
    )
    assert response.status_code == 401
    async with api.database.sessions() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(RefreshToken)
                .where(RefreshToken.revoked_at.is_(None))
            )
            == 0
        )


async def test_forced_change_and_logout(api):
    async with api.database.sessions.begin() as session:
        user = await session.get(User, api.users["employee"].id)
        user.must_change_password = True
    login = await full_login(api, "employee")
    headers = {
        "Authorization": "Bearer " + login.json()["access_token"],
        "X-CSRF-Token": login.json()["csrf_token"],
    }
    assert (await api.client.get("/api/v1/cities", headers=headers)).status_code == 403
    assert (await api.client.get("/api/v1/auth/me", headers=headers)).status_code == 200
    response = await api.client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": "ValidPass123", "new_password": "ChangedPass123"},
    )
    assert response.status_code == 204, response.text
    assert (await api.client.get("/api/v1/cities", headers=headers)).status_code == 200
    assert (await api.client.post("/api/v1/auth/logout", headers=headers)).status_code == 204
    assert api.client.cookies.get("crm_refresh") is None


@pytest.mark.parametrize("change", ["deactivate", "delete", "reset-password", "mobile"])
async def test_pending_challenge_invalidated_by_account_changes(api, change):
    first = (await first_factor(api, "employee")).json()
    user_id = api.users["employee"].id
    if change == "mobile":
        response = await api.client.patch(
            f"/api/v1/users/{user_id}",
            headers=api.headers["supervisor"],
            json={"mobile": "09123456999"},
        )
    elif change == "delete":
        response = await api.client.delete(
            f"/api/v1/users/{user_id}", headers=api.headers["supervisor"]
        )
    else:
        response = await api.client.post(
            f"/api/v1/users/{user_id}/{change}", headers=api.headers["supervisor"]
        )
    assert response.status_code in {200, 204}, response.text
    verified = await api.client.post(
        "/api/v1/auth/verify-sms", json={"challenge_id": first["challenge_id"], "code": "123"}
    )
    assert verified.status_code == 401


async def test_swagger_declares_bearer_auth_for_protected_endpoints(api):
    spec = (await api.client.get("/openapi.json")).json()
    assert spec["components"]["securitySchemes"]["BearerAuth"] == {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }
    me_path = "/api/v1/auth/me"
    assert spec["paths"][me_path]["get"]["security"] == [{"BearerAuth": []}]
    assert "security" not in spec["paths"]["/api/v1/auth/verify-sms"]["post"]

    for headers in ({}, {"Authorization": "Basic test"}, {"Authorization": "Bearer invalid"}):
        response = await api.client.get(me_path, headers=headers)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"
    assert (await api.client.get(me_path, headers=api.headers["supervisor"])).status_code == 200
