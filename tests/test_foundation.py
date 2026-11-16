import json
import logging
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from app.main import create_app


async def test_errors_tracing_and_redaction(settings, caplog):
    app = create_app(settings)

    class Input(BaseModel):
        amount: int

    @app.post("/test-input")
    async def parse(body: Input):
        return body

    @app.get("/test-failure")
    async def failure():
        raise RuntimeError("password=SensitivePass123 token=secret 09123456789")

    caplog.set_level(logging.INFO, logger="crm.requests")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        request_id = str(uuid4())
        responses = [
            await client.get("/missing", headers={"X-Request-ID": request_id}),
            await client.post(
                "/test-input", content="{", headers={"Content-Type": "application/json"}
            ),
            await client.post("/test-input", json={"amount": "SensitivePass123"}),
            await client.get("/test-failure"),
            await client.get("/missing", headers={"X-Request-ID": "not-a-uuid"}),
        ]
    assert [r.status_code for r in responses] == [404, 400, 422, 500, 404]
    assert responses[0].headers["x-request-id"] == request_id
    for response in responses:
        error = response.json()["error"]
        assert set(error) == {"code", "message", "details", "request_id"}
        assert str(UUID(error["request_id"])) == response.headers["x-request-id"]
        assert "SensitivePass123" not in response.text
    assert "SensitivePass123" not in caplog.text
    assert "09123456789" not in caplog.text
    for record in caplog.records:
        if record.name == "crm.requests":
            assert "request_id" in json.loads(record.message)


async def test_health_and_database_failure(settings, database):
    app = create_app(settings)
    app.state.database = database
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/v1/health")).status_code == 200
        assert (await client.get("/api/v1/health/ready")).status_code == 200

        def unavailable():
            raise RuntimeError("secret connection URL")

        app.state.database = type("Unavailable", (), {"sessions": staticmethod(unavailable)})()
        response = await client.get("/api/v1/health/ready")
        assert response.status_code == 503
        assert "secret" not in response.text
        assert (await client.get("/api/v1/health")).status_code == 200
