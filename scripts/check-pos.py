"""Exercise POS through a local test proxy with synthetic staff and XLSX files.

Requires a fresh dev-only Supervisor (09170000000 / PosSmokeValid123) in the
isolated smoke project. Never point this script at production.
"""

import argparse
import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx

from app.core.excel import workbook_bytes


def expected(response, status):
    assert response.status_code == status, (
        f"{response.request.method} {response.request.url.path}: {response.status_code}"
    )
    assert str(UUID(response.headers["x-request-id"])) == response.headers["x-request-id"]
    return response.json() if response.content else None


def login(client, mobile, password):
    challenge = expected(
        client.post("/api/v1/auth/login", json={"mobile": mobile, "password": password}), 202
    )
    session = expected(
        client.post(
            "/api/v1/auth/verify-sms",
            json={"challenge_id": challenge["challenge_id"], "code": "123"},
        ),
        200,
    )
    client.headers["Authorization"] = "Bearer " + session["access_token"]
    client.headers["X-CSRF-Token"] = session["csrf_token"]
    me = expected(client.get("/api/v1/auth/me"), 200)
    if me["must_change_password"]:
        expected(
            client.post(
                "/api/v1/auth/change-password",
                json={"current_password": password, "new_password": "PosSmokeChanged456"},
            ),
            204,
        )


def main(args):
    url = urlsplit(args.base_url)
    if url.hostname not in {"localhost", "127.0.0.1"}:
        raise SystemExit("Only local disposable deployments are allowed")
    evidence = {}
    clients = [
        httpx.Client(
            base_url=args.base_url,
            headers={"Origin": "http://localhost:5173"},
            timeout=60,
            trust_env=False,
        )
        for _ in range(3)
    ]
    supervisor, manager, employee = clients
    try:
        for _ in range(30):
            if supervisor.get("/api/v1/health/ready").status_code == 200:
                break
            time.sleep(1)
        expected(supervisor.get("/api/v1/health/ready"), 200)
        login(supervisor, "09170000000", os.environ.get("POS_SMOKE_PASSWORD", "PosSmokeValid123"))
        if args.verify_original:
            saved = json.loads(Path(args.verify_original).read_text())
            response = supervisor.get(saved["original_url"])
            assert response.status_code == 200
            assert hashlib.sha256(response.content).hexdigest() == saved["original_sha256"]
            saved["persistence_after_container_recreation"] = True
            Path(args.output).write_text(json.dumps(saved, indent=2) + "\n")
            print("Original XLSX persisted across API container recreation")
            return
        suffix = uuid4().hex[:8].upper()
        city = expected(
            supervisor.post("/api/v1/cities", json={"name": "Synthetic POS Smoke " + suffix}), 201
        )
        branch = expected(
            supervisor.post(
                "/api/v1/branches",
                json={
                    "city_id": city["id"],
                    "name": "Synthetic Branch " + suffix,
                    "code": "00" + suffix,
                },
            ),
            201,
        )
        staff = []
        for role, client in [("branch_manager", manager), ("employee", employee)]:
            mobile = "0918" + "".join(str(secrets.randbelow(10)) for _ in range(7))
            user = expected(
                supervisor.post(
                    "/api/v1/users",
                    json={
                        "first_name": "Synthetic",
                        "last_name": role,
                        "mobile": mobile,
                        "role": role,
                        "branch_id": branch["id"],
                    },
                ),
                201,
            )
            login(client, mobile, user["temporary_password"])
            staff.append(user)
        device_code = "SMOKE-" + suffix
        registry = workbook_bytes(
            ["device_number", "branch_code", "owner_name", "address", "account_number"],
            [
                [
                    device_code,
                    branch["code"],
                    "Synthetic Owner",
                    "Synthetic smoke address",
                    "00123456",
                ]
            ],
        )
        response = supervisor.post(
            "/api/v1/pos/imports/devices", files={"file": ("synthetic.xlsx", registry)}
        )
        log = expected(response, 200)
        assert log["created"] == 1
        evidence["import_id"] = log["id"]
        evidence["original_sha256"] = hashlib.sha256(registry).hexdigest()
        evidence["original_url"] = log["file_url"]
        original = supervisor.get(log["file_url"])
        assert original.status_code == 200 and original.content == registry
        expected(manager.get(log["file_url"]), 403)
        expected(manager.get(log["errors_url"]), 403)
        errors = supervisor.get(log["errors_url"], params={"format": "xlsx"})
        assert errors.status_code == 200 and errors.content.startswith(b"PK")
        activity = workbook_bytes(
            ["device_number", "transaction_amount", "transaction_count"],
            [[device_code, "100000000.00", 5]],
        )
        tx = expected(
            supervisor.post(
                "/api/v1/pos/imports/transactions",
                files={"file": ("synthetic.xlsx", activity)},
                data={"jalali_year": 1405, "jalali_month": 7},
            ),
            200,
        )
        assert tx["created"] == 1
        device = expected(supervisor.get("/api/v1/pos/devices", params={"q": device_code}), 200)[
            "items"
        ][0]
        rank = expected(
            supervisor.get(
                "/api/v1/pos/productivity",
                params={"jalali_year": 1405, "jalali_month": 7, "branch_id": branch["id"]},
            ),
            200,
        )
        assert rank["items"][0]["performance"] == "low"
        selected = expected(
            supervisor.post(
                "/api/v1/pos/visits/dispatch",
                json={"pos_device_ids": [device["id"]], "jalali_year": 1405, "jalali_month": 7},
            ),
            200,
        )[0]
        visit_id = selected["visit_id"]
        queue = expected(
            manager.get("/api/v1/pos/visits", params={"status": "pending_assignment"}), 200
        )
        assert queue["total"] == 1
        expected(
            manager.post(
                "/api/v1/pos/visits/" + visit_id + "/assign", json={"assigned_to": staff[1]["id"]}
            ),
            200,
        )
        expected(
            employee.post(
                "/api/v1/pos/visits/" + visit_id + "/complete",
                json={
                    "result": "visited",
                    "tag_codes": ["maintenance_required"],
                    "description": "Synthetic smoke completion",
                },
            ),
            200,
        )
        saved = expected(employee.get("/api/v1/pos/visits/" + visit_id), 200)
        assert saved["selection_snapshot"]["amount"] == "100000000.00"
        expected(employee.get("/api/v1/pos/devices"), 403)
        assert (
            expected(employee.get("/api/v1/pos/reports/summary"), 200)["completed_in_30_days"] == 1
        )
        large = supervisor.post(
            "/api/v1/pos/imports/devices",
            files={"file": ("large.xlsx", b"x" * (10 * 1024 * 1024 + 1))},
        )
        assert large.status_code == 413 and large.json()["error"]["code"] == "file_too_large"
        proxy_large = supervisor.post(
            "/api/v1/pos/imports/devices", content=b"x" * (12 * 1024 * 1024 + 1)
        )
        assert (
            proxy_large.status_code == 413
            and proxy_large.json()["error"]["code"] == "file_too_large"
        )
        for response in (large, proxy_large):
            assert response.json()["error"]["request_id"] == response.headers["x-request-id"]
        evidence["checks"] = [
            "password/SMS/cookie/CSRF forced change",
            "English XLSX imports",
            "rial performance",
            "Supervisor dispatch",
            "manager queue/assignment",
            "employee completion",
            "immutable evidence",
            "role-scoped reports",
            "original/error download authorization",
            "application/proxy upload limits",
        ]
        Path(args.output).write_text(json.dumps(evidence, indent=2) + "\n")
        print("POS browser/proxy smoke flow passed; evidence:", args.output)
    finally:
        for client in clients:
            client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8081")
    parser.add_argument("--output", default="/tmp/pos-smoke.json")
    parser.add_argument("--verify-original")
    main(parser.parse_args())
