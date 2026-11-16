import asyncio

import httpx
import pytest
from argon2 import PasswordHasher
from sqlalchemy import func, select

from app.core.sms import SmsAdapter, SmsDeliveryError
from app.models import LoginChallenge, RefreshToken, User
from tests.test_auth import first_factor, full_login


async def test_concurrent_password_failures(api):
    responses = await asyncio.gather(*[first_factor(api, password="wrong") for _ in range(5)])
    assert all(response.status_code == 401 for response in responses)
    async with api.database.sessions() as session:
        user = await session.get(User, api.users["supervisor"].id)
        assert user.failed_login_count == 5 and user.locked_until is not None


async def test_concurrent_refresh_and_csrf_binding(api):
    response = await full_login(api)
    raw = api.client.cookies.get("crm_refresh")
    headers = {"Cookie": f"crm_refresh={raw}", "X-CSRF-Token": response.json()["csrf_token"]}
    responses = await asyncio.gather(
        *[api.client.post("/api/v1/auth/refresh", headers=headers) for _ in range(2)]
    )
    assert sorted(response.status_code for response in responses) == [200, 401]
    async with api.database.sessions() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(RefreshToken)
                .where(RefreshToken.revoked_at.is_(None))
            )
            == 0
        )


async def test_origin_and_csrf_rejection_do_not_mutate(api):
    response = await full_login(api)
    csrf = response.json()["csrf_token"]
    for headers in (
        {"X-CSRF-Token": "wrong"},
        {"X-CSRF-Token": csrf, "Origin": "https://attacker.example"},
        {"X-CSRF-Token": csrf, "Origin": ""},
    ):
        assert (await api.client.post("/api/v1/auth/refresh", headers=headers)).status_code == 403
    async with api.database.sessions() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(RefreshToken)
                .where(RefreshToken.revoked_at.is_(None))
            )
            == 1
        )


async def test_pending_delivery_and_concurrent_send_cooldown(api):
    responses = await asyncio.gather(first_factor(api), first_factor(api))
    assert sorted(response.status_code for response in responses) == [202, 429]
    async with api.database.sessions.begin() as session:
        challenge = await session.scalar(
            select(LoginChallenge).where(LoginChallenge.invalidated_at.is_(None))
        )
        challenge.delivery_state = "pending"
        challenge_id = str(challenge.id)
    response = await api.client.post(
        "/api/v1/auth/verify-sms", json={"challenge_id": challenge_id, "code": "123"}
    )
    assert response.status_code == 401


async def test_rehash_and_unknown_user_response(api):
    old_hash = PasswordHasher(time_cost=1, memory_cost=8192).hash("ValidPass123")
    async with api.database.sessions.begin() as session:
        user = await session.get(User, api.users["supervisor"].id)
        user.password_hash = old_hash
    response = await first_factor(api)
    assert response.status_code == 202
    async with api.database.sessions() as session:
        assert (await session.get(User, api.users["supervisor"].id)).password_hash != old_hash
    wrong = await first_factor(api, "employee", password="wrong")
    unknown = await api.client.post(
        "/api/v1/auth/login", json={"mobile": "09999999999", "password": "wrong"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["code"] == unknown.json()["error"]["code"]


@pytest.mark.parametrize("failure", [None, "timeout", "rejected", "malformed", "status"])
async def test_http_sms_adapter_contract(settings, monkeypatch, failure):
    original = httpx.AsyncClient
    captured = []

    def provider(request):
        captured.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("test timeout")
        if failure == "malformed":
            return httpx.Response(200, json=[])
        if failure == "status":
            return httpx.Response(503)
        return httpx.Response(200, json={"accepted": failure != "rejected"})

    monkeypatch.setattr(
        "app.core.sms.httpx.AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(provider), **kwargs),
    )
    config = type(settings)(
        _env_file=None,
        **(
            settings.model_dump()
            | {
                "environment": "production",
                "sms_mode": "http",
                "sms_url": "https://sms.example.test/send",
                "sms_api_key": "test-key",
            }
        ),
    )
    adapter = SmsAdapter(config)
    code = adapter.generate_code()
    assert len(code) == 6 and code.isascii() and code.isdigit()
    if failure:
        with pytest.raises(SmsDeliveryError):
            await adapter.send("09123456789", code)
    else:
        await adapter.send("09123456789", code)
    assert len(captured) == 1


async def test_dev_sms_never_calls_http(settings, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Development must not call provider")

    monkeypatch.setattr("app.core.sms.httpx.AsyncClient", forbidden)
    adapter = SmsAdapter(settings)
    assert adapter.generate_code() == "123"
    await adapter.send("09123456789", "123")
