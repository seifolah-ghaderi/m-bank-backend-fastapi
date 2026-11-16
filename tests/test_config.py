import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app


def test_required_secrets(monkeypatch):
    for name in ("DATABASE_URL", "JWT_SECRET", "CSRF_SECRET", "SMS_DIGEST_SECRET"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_no_secrets_in_validation(settings):
    values = settings.model_dump()
    values["jwt_secret"] = "too-short-sensitive"
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, **values)
    assert "too-short-sensitive" not in str(error.value)


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_fixed_sms_forbidden(settings, environment):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **(settings.model_dump() | {"environment": environment}))


async def test_cors_and_production_docs(settings):
    values = settings.model_dump() | {
        "environment": "production",
        "sms_mode": "http",
        "sms_url": "https://sms.example.test/send",
        "sms_api_key": "test-credential",
    }
    app = create_app(Settings(_env_file=None, **values))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert (await client.get(path)).status_code == 404
        headers = {
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-CSRF-Token,Content-Type",
        }
        response = await client.options("/api/v1/auth/refresh", headers=headers)
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == headers["Origin"]
        assert response.headers["access-control-allow-credentials"] == "true"
        headers["Origin"] = "https://attacker.example"
        response = await client.options("/api/v1/auth/refresh", headers=headers)
        assert "access-control-allow-origin" not in response.headers


def test_wildcard_origin_rejected(settings):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **(settings.model_dump() | {"cors_origins": ["*"]}))
