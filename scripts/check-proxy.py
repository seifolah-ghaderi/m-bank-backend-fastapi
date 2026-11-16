"""Smoke-test the local Compose proxy without modifying application records."""

import time
from uuid import UUID, uuid4

import httpx

with httpx.Client(base_url="http://localhost:8080", timeout=30, trust_env=False) as client:
    request_id = str(uuid4())
    for _ in range(30):
        response = client.get("/api/v1/health/ready", headers={"X-Request-ID": request_id})
        if response.status_code == 200:
            break
        time.sleep(1)
    assert response.status_code == 200, response.text
    assert response.headers["x-request-id"] == request_id
    response = client.post("/api/v1/auth/verify-sms", content=b"x" * (12 * 1024 * 1024 + 1))
    assert response.status_code == 413, response.text
    assert response.json()["error"]["code"] == "file_too_large"
    assert str(UUID(response.json()["error"]["request_id"])) == response.headers["x-request-id"]
    responses = [client.post("/api/v1/auth/login", json={}) for _ in range(11)]
    assert any(response.status_code == 429 for response in responses)
    for response in responses:
        if response.status_code == 429:
            assert response.json()["error"]["code"] == "too_many_requests"
            assert response.json()["error"]["request_id"] == response.headers["x-request-id"]
print("Proxy readiness, tracing, 12 MB limit, and login rate limit passed.")
