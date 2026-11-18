import asyncio
from datetime import timedelta
from uuid import UUID

from sqlalchemy import event, func, select

from app.core import dates
from app.core.db import Database
from app.models import (
    AuditLog,
    Customer,
    CustomerProduct,
    Lead,
    Notification,
    ProductSale,
    RetentionTask,
    SaleDecision,
    SaleSubmission,
    ScoreTransaction,
    User,
)
from tests.test_marketing_campaigns import (
    add_attempt,
    create_campaign,
    create_lead,
    make_employee,
    work_urls,
)


async def product(api, code, score=5):
    result = await api.client.post(
        "/api/v1/banking-products",
        headers=api.headers["supervisor"],
        json={"name": f"Product {code}", "code": code, "score_value": score},
    )
    assert result.status_code == 201, result.text
    return result.json()["id"]


async def start_visit(api, lead, *, cross_sell=False, repeat=False):
    campaign = await create_campaign(api, [lead], include_customers=cross_sell, activate=True)
    (work,) = await work_urls(api, campaign)
    picked = await api.client.post(work + "/pick", headers=api.headers["employee"])
    assert picked.status_code == 200, picked.text
    visit = await add_attempt(api, work)
    assert visit.status_code == 201, visit.text
    if repeat:
        visit = await add_attempt(api, work, description="Repeat contact")
        assert visit.json()["visit_count"] == 2
    return campaign, work, visit.json()["id"]


async def registration(
    api, visit, banking_product, *, code=None, proof="Checked bank reference", employee="employee"
):
    payload = {
        "visit_id": visit,
        "banking_product_id": banking_product,
        "account_number": "۰۰۱۲۳",
        "proof_text": proof,
    }
    if code:
        payload["customer_profile"] = {"customer_code": code, "first_name": "Verified"}
    return await api.client.post("/api/v1/sales", headers=api.headers[employee], json=payload)


async def register(api, visit, banking_product, **kwargs):
    response = await registration(api, visit, banking_product, **kwargs)
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def submit(api, ids, role="employee"):
    return await api.client.post(
        "/api/v1/sales/submit", headers=api.headers[role], json={"sale_ids": ids}
    )


async def evidence(api):
    response = await api.client.get("/api/v1/verifications", headers=api.headers["supervisor"])
    assert response.status_code == 200, response.text
    return {
        item["sale"]["id"]: item["submission"]
        for group in response.json()["items"]
        for item in group["sales"]
    }


async def decide(api, sale, revision, action="approve", role="supervisor", **payload):
    return await api.client.post(
        f"/api/v1/sales/{sale}/{action}",
        headers=api.headers[role],
        json={"submission_id": revision} | payload,
    )


async def schedule(api, days, **kwargs):
    return await api.client.post(
        "/api/v1/retention-schedules",
        headers=api.headers["supervisor"],
        json={"label": f"Day {days}", "days_after_conversion": days} | kwargs,
    )


async def test_prefill_drafts_and_atomic_submission(api):
    first = await product(api, "P1")
    second = await product(api, "P2")
    _, _, visit = await start_visit(api, await create_lead(api))
    url = f"/api/v1/visits/{visit}/sales-form"
    response = await api.client.get(url, headers=api.headers["employee"])
    profile = response.json()["customer_profile"]
    assert profile["first_name"] == "Sara"
    assert profile["customer_code"] is None
    assert (await api.client.get(url, headers=api.headers["other"])).status_code == 404
    assert (await registration(api, visit, first, employee="other")).status_code == 404

    one = await register(api, visit, first, code="۰۰۴۲")
    assert (await registration(api, visit, first)).status_code == 409
    two = await register(api, visit, second, proof=" a b c d ")
    denied = await submit(api, [one, two])
    assert denied.status_code == 422 and denied.json()["error"]["details"]["sale_id"] == two
    listing = await api.client.get("/api/v1/sales", headers=api.headers["employee"])
    assert {row["status"] for row in listing.json()["items"]} == {"draft"}
    patched = await api.client.patch(
        f"/api/v1/sales/{two}", headers=api.headers["employee"], json={"proof_text": "Bank checked"}
    )
    assert patched.status_code == 200, patched.text
    response = await submit(api, [one, two])
    assert response.status_code == 200, response.text
    rows = await evidence(api)
    assert rows[one]["profile"]["customer_code"] == "0042"
    assert rows[one]["account_number"] == "00123"
    assert rows[two]["proof_text"] == "Bank checked"


async def test_reject_resubmit_after_reassignment_and_close(api):
    user = await make_employee(api)
    p = await product(api, "P1")
    campaign, work, visit = await start_visit(api, await create_lead(api))
    sale = await register(api, visit, p, code="007")
    assert (await submit(api, [sale])).status_code == 200
    old = (await evidence(api))[sale]["id"]
    assert (
        await decide(api, sale, old, "reject", "employee", reason="Account invalid")
    ).status_code == 403
    rejected = await decide(api, sale, old, "reject", reason="Account invalid")
    assert rejected.status_code == 200, rejected.text
    move = await api.client.post(
        work + "/reassign", headers=api.headers["manager"], json={"employee_id": str(user.id)}
    )
    assert move.status_code == 200, move.text
    assert (
        await api.client.post(campaign + "/close", headers=api.headers["supervisor"])
    ).status_code == 200
    assert (await registration(api, visit, p, employee="second")).status_code == 409
    update = await api.client.patch(
        f"/api/v1/sales/{sale}",
        headers=api.headers["employee"],
        json={"account_number": "00456", "proof_text": "Checked again"},
    )
    assert update.status_code == 200, update.text
    assert (await submit(api, [sale])).status_code == 200
    current = (await evidence(api))[sale]["id"]
    assert current != old
    assert (await decide(api, sale, old)).status_code == 409
    assert (
        await api.client.get(f"/api/v1/sales/{sale}", headers=api.headers["second"])
    ).status_code == 404
    notifications = await api.client.get("/api/v1/notifications", headers=api.headers["employee"])
    assert notifications.json()["items"][0]["payload"] == {"sale_id": sale}
    hidden = await api.client.get("/api/v1/notifications", headers=api.headers["second"])
    assert hidden.json()["total"] == 0
    async with api.database.sessions() as db:
        assert (await db.get(SaleSubmission, UUID(old))).proof_text == "Checked bank reference"
        previous = await db.scalar(
            select(SaleDecision).where(SaleDecision.submission_id == UUID(old))
        )
        assert previous.reason == "Account invalid"
        assert await db.scalar(select(func.count()).select_from(ScoreTransaction)) == 0


async def test_end_to_end_partial_batch_cross_sell_and_customer_scope(api):
    assert (await schedule(api, 15)).status_code == 201
    assert (await schedule(api, 15)).status_code == 409
    assert (await schedule(api, 0)).status_code == 422
    assert (await schedule(api, 45, requires_approval=True)).status_code == 201
    assert (await schedule(api, 90, is_active=False)).status_code == 201
    products = [await product(api, f"P{n}", score=n) for n in range(1, 5)]
    lead = await create_lead(api)
    campaign, work, visit = await start_visit(api, lead, repeat=True)
    sales = [await register(api, visit, p, code="0042") for p in products[:3]]
    assert (await submit(api, sales)).status_code == 200
    assert (
        await api.client.post(work + "/complete", headers=api.headers["employee"])
    ).status_code == 200
    by_sale = await evidence(api)
    first = await decide(api, sales[0], by_sale[sales[0]]["id"])
    assert first.status_code == 200, first.text
    customer = first.json()["customer"]
    assert customer["first_name"] == "Verified"
    assert customer["customer_code"] == "0042"
    by_sale = await evidence(api)
    assert set(by_sale) == set(sales[1:])
    path = f"/api/v1/verifications/visits/{visit}/approve"
    reviewed = [{"sale_id": key, "submission_id": value["id"]} for key, value in by_sale.items()]
    conflict = await api.client.post(
        path,
        headers=api.headers["supervisor"],
        json={"sales": reviewed + [{"sale_id": sales[0], "submission_id": str(UUID(int=0))}]},
    )
    assert conflict.status_code == 409
    assert set(await evidence(api)) == set(sales[1:])
    batch = await api.client.post(path, headers=api.headers["supervisor"], json={"sales": reviewed})
    assert batch.status_code == 200, batch.text
    assert len(batch.json()["sales"]) == 2
    assert await evidence(api) == {}

    detail_url = "/api/v1/customers/" + customer["id"]
    manager = await api.client.get(detail_url, headers=api.headers["manager"])
    assert manager.status_code == 200, manager.text
    detail = manager.json()
    assert len(detail["products"]) == 3
    assert "account_number" not in detail["products"][0]
    assert "proof_text" not in detail["sales"][0]
    assert [item["status"] for item in detail["retention_tasks"]] == ["open", "pending_approval"]
    assert detail["retention_tasks"][0]["due_date"] == dates.format_date(
        dates.today() + timedelta(days=15)
    )
    assert (await api.client.get(detail_url, headers=api.headers["employee"])).status_code == 403
    listing = await api.client.get(
        "/api/v1/customers",
        headers=api.headers["manager"],
        params={
            "customer_since_from": dates.format_date(dates.today()),
            "q": "verified",
            "product_id": products[0],
        },
    )
    assert listing.status_code == 200, listing.text
    assert listing.json()["total"] == 1
    async with api.database.sessions.begin() as db:
        (await db.get(User, api.users["other"].id)).role = "branch_manager"
    assert (await api.client.get(detail_url, headers=api.headers["other"])).status_code == 404
    patch = await api.client.patch(
        detail_url, headers=api.headers["manager"], json={"phone": "02122223333"}
    )
    assert patch.status_code == 200 and patch.json()["phone"] == "02122223333"

    assert (
        await api.client.post(campaign + "/close", headers=api.headers["supervisor"])
    ).status_code == 200
    _, _, cross_visit = await start_visit(api, lead, cross_sell=True)
    form = await api.client.get(
        f"/api/v1/visits/{cross_visit}/sales-form", headers=api.headers["employee"]
    )
    assert form.json()["customer_id"] == customer["id"]
    assert len(form.json()["held_products"]) == 3
    assert (await registration(api, cross_visit, products[0])).status_code == 409
    new = await register(api, cross_visit, products[3])
    assert (await submit(api, [new])).status_code == 200
    changed = await api.client.patch(
        f"/api/v1/banking-products/{products[3]}",
        headers=api.headers["supervisor"],
        json={"score_value": 9},
    )
    assert changed.status_code == 200
    revision = (await evidence(api))[new]["id"]
    result = await decide(api, new, revision)
    assert result.status_code == 200, result.text
    assert result.json()["customer"]["id"] == customer["id"]
    result_lead = await api.client.get(
        f"/api/v1/leads/{lead['id']}", headers=api.headers["supervisor"]
    )
    assert result_lead.json()["first_name"] == "Sara" and result_lead.json()["is_customer"]
    async with api.database.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(RetentionTask)) == 2
        scores = list(
            await db.scalars(select(ScoreTransaction.points).order_by(ScoreTransaction.points))
        )
        assert scores == [1, 2, 3, 9]
        assert await db.scalar(select(func.count()).select_from(Notification)) == 4
        log = await db.scalar(select(AuditLog).where(AuditLog.action == "update_contact"))
        assert log.after == {"fields": ["phone"]}


async def test_concurrent_approvals_and_duplicate_customer_code(api):
    await schedule(api, 15)
    p1, p2 = await product(api, "P1"), await product(api, "P2")
    _, _, visit = await start_visit(api, await create_lead(api))
    _, _, second_visit = await start_visit(api, await create_lead(api, 2))
    one, two = await register(api, visit, p1, code="042"), await register(api, visit, p2)
    collision = await register(api, second_visit, p1, code="042")
    assert (await submit(api, [one, two])).status_code == 200
    assert (await submit(api, [collision])).status_code == 200
    revisions = await evidence(api)
    results = await asyncio.gather(*(decide(api, ref, revisions[ref]["id"]) for ref in (one, two)))
    assert all(r.status_code == 200 for r in results), [r.text for r in results]
    assert results[0].json()["customer"]["id"] == results[1].json()["customer"]["id"]
    failed = await decide(api, collision, revisions[collision]["id"])
    assert failed.status_code == 409 and failed.json()["error"]["code"] == "customer_code_exists"
    assert (await decide(api, one, revisions[one]["id"])).status_code == 409
    async with api.database.sessions() as db:
        for model, expected in (
            (Customer, 1),
            (RetentionTask, 1),
            (CustomerProduct, 2),
            (ScoreTransaction, 2),
            (Notification, 2),
        ):
            assert await db.scalar(select(func.count()).select_from(model)) == expected


async def test_approval_side_effects_roll_back_together(api):
    await schedule(api, 15)
    lead = await create_lead(api)
    _, _, visit = await start_visit(api, lead)
    sale = await register(api, visit, await product(api, "P1"), code="369")
    assert (await submit(api, [sale])).status_code == 200
    revisions = await evidence(api)
    async with api.database.sessions.begin() as db:
        db.add(
            ScoreTransaction(
                source_id=UUID(sale),
                employee_id=api.users["employee"].id,
                points=10,
                occurred_at=dates.now(),
            )
        )
    failed = await decide(api, sale, revisions[sale]["id"])
    assert failed.status_code == 409
    async with api.database.sessions() as db:
        assert (await db.get(ProductSale, UUID(sale))).status == "submitted"
        assert not (await db.get(Lead, UUID(lead["id"]))).is_customer
        for model in (Customer, CustomerProduct, RetentionTask, Notification, SaleDecision):
            assert await db.scalar(select(func.count()).select_from(model)) == 0


async def test_campaign_and_approval_with_runtime_privileges(api):
    runtime = Database(api.database.engine.url.render_as_string(hide_password=False))

    @event.listens_for(runtime.engine.sync_engine, "connect")
    def set_role(connection, _):
        cursor = connection.cursor()
        cursor.execute("SET ROLE crm_runtime")
        cursor.close()
        connection.commit()

    api.app.state.database = runtime
    try:
        assert (await schedule(api, 15)).status_code == 201
        p = await product(api, "P1")
        _, _, visit = await start_visit(api, await create_lead(api))
        sale = await register(api, visit, p, code="4092")
        assert (await submit(api, [sale])).status_code == 200
        revision = (await evidence(api))[sale]["id"]
        decision = await decide(api, sale, revision)
        assert decision.status_code == 200, decision.text
    finally:
        api.app.state.database = api.database
        await runtime.close()
