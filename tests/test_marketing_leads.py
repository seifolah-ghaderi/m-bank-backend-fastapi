from uuid import UUID

from sqlalchemy import select

from app.core import dates
from app.models import (
    AuditLog,
    BankingProduct,
    Branch,
    Campaign,
    CampaignLead,
    CampaignVisit,
    Lead,
    ProductSale,
)


async def test_manual_lead_creation_search_and_identity(api):
    client = api.client
    url = "/api/v1/leads"
    supervisor = api.headers["supervisor"]
    payload = {
        "branch_id": str(api.branches[0].id),
        "city_id": str(api.city.id),
        "first_name": "علي",
        "last_name": " كاظمي ",
        "mobile": "+۹۸ ۹۱۲ ۱۱۱ ۲۲۳۳",
        "national_code": "۰۰۱۳۵۴۱۹۰۰",
    }
    employee = api.headers["employee"]
    assert (await client.post(url, headers=employee, json=payload)).status_code == 403
    assert (await client.get(url, headers=employee)).status_code == 403
    created = await client.post(url, headers=supervisor, json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["mobile"] == "09121112233"
    assert (await client.post(url, headers=supervisor, json=payload)).status_code == 409
    conflicting = dict(payload, mobile="09121112234")
    assert (await client.post(url, headers=supervisor, json=conflicting)).status_code == 409
    result = await client.get(url, headers=supervisor, params={"q": "علي كاظمي"})
    assert result.json()["total"] == 1

    async with api.database.sessions.begin() as session:
        branch = await session.get(Branch, api.branches[1].id)
        branch.is_active = False
    conflicting.update(national_code=None, branch_id=str(api.branches[1].id))
    assert (await client.post(url, headers=supervisor, json=conflicting)).status_code == 422


async def test_archive_guards_and_history(api):
    user = api.users["supervisor"]
    branch = api.branches[0]
    url = "/api/v1/leads"
    headers = api.headers["supervisor"]
    async with api.database.sessions.begin() as session:
        lead = Lead(
            branch_id=branch.id,
            city_id=api.city.id,
            first_name="Test",
            last_name="Lead",
            mobile="09121112233",
        )
        campaign = Campaign(
            title="Archive", start_date=dates.today(), end_date=dates.today(), status="active"
        )
        product = BankingProduct(name="Loan", code="ARCH", score_value=1)
        session.add_all((lead, campaign, product))
        await session.flush()
        membership = CampaignLead(
            campaign_id=campaign.id,
            lead_id=lead.id,
            branch_id=branch.id,
            assigned_to_branch_at=dates.now(),
            reserved=True,
        )
        session.add(membership)
        await session.flush()
        visit = CampaignVisit(
            campaign_lead_id=membership.id,
            employee_id=api.users["employee"].id,
            visit_date=dates.today(),
            result="interested",
            visit_count=1,
            last_visited_at=dates.now(),
        )
        session.add(visit)
        await session.flush()
        sale = ProductSale(
            visit_id=visit.id,
            lead_id=lead.id,
            banking_product_id=product.id,
            employee_id=api.users["employee"].id,
            account_number="1",
            registered_at=dates.now(),
        )
        session.add(sale)
    archive = f"{url}/{lead.id}/archive"
    assert (await api.client.post(archive, headers=headers)).status_code == 409

    async with api.database.sessions.begin() as session:
        (await session.get(CampaignLead, membership.id)).reserved = False
    assert (await api.client.post(archive, headers=headers)).status_code == 409
    async with api.database.sessions.begin() as session:
        (await session.get(ProductSale, sale.id)).status = "withdrawn"
        (await session.get(Lead, lead.id)).is_customer = True
    assert (await api.client.post(archive, headers=headers)).status_code == 409
    async with api.database.sessions.begin() as session:
        (await session.get(Lead, lead.id)).is_customer = False
    assert (await api.client.post(archive, headers=headers)).status_code == 200
    assert (await api.client.get(url, headers=headers)).json()["total"] == 0
    archived = await api.client.get(url, headers=headers, params={"archived": True})
    assert UUID(archived.json()["items"][0]["id"]) == lead.id
    assert (await api.client.post(f"{url}/{lead.id}/restore", headers=headers)).status_code == 200
    async with api.database.sessions() as session:
        assert await session.get(ProductSale, sale.id)
        actions = await session.scalars(
            select(AuditLog.action).where(
                AuditLog.actor_id == user.id, AuditLog.entity_id == lead.id
            )
        )
        assert set(actions) == {"archive", "restore"}
