from sqlalchemy import and_, func, select

from app.core import dates
from app.core.audit import record
from app.core.deps import require_roles
from app.core.errors import DomainError
from app.core.pagination import paginate
from app.core.validation import input_values, validated_changes
from app.features.marketing.work import get_member
from app.models import (
    BankingProduct,
    Campaign,
    CampaignLead,
    CampaignVisit,
    City,
    Customer,
    CustomerDraft,
    CustomerProduct,
    Lead,
    Notification,
    ProductSale,
    SaleDecision,
    SaleSubmission,
)
from app.schemas.sales import CustomerProfile, SaleOut, SaleSubmissionOut

EDITABLE = ("draft", "rejected")
SALE_SORTS = {
    "registered_at": ProductSale.registered_at,
    "last_submitted_at": ProductSale.last_submitted_at,
}


def own_sales(user):
    require_roles(user, "employee")
    return (
        select(ProductSale)
        .join(Lead, ProductSale.lead_id == Lead.id)
        .where(ProductSale.employee_id == user.id, Lead.branch_id == user.branch_id)
    )


async def sale_list(session, user, page, status):
    statement = own_sales(user)
    if status:
        statement = statement.where(ProductSale.status == status)
    return await paginate(session, statement, page, SALE_SORTS, "-registered_at", ProductSale.id)


async def sale_detail(session, user, sale_id):
    sale = await session.scalar(own_sales(user).where(ProductSale.id == sale_id))
    if sale is None:
        raise DomainError(404, "not_found")
    return sale


async def visit_context(session, user, visit_id, *, mutate=False):
    require_roles(user, "employee")
    route = (
        await session.execute(
            select(CampaignLead.id, CampaignLead.campaign_id)
            .join(CampaignVisit, CampaignVisit.campaign_lead_id == CampaignLead.id)
            .join(Campaign, Campaign.id == CampaignLead.campaign_id)
            .where(
                CampaignVisit.id == visit_id,
                CampaignLead.locked_by == user.id,
                CampaignLead.branch_id == user.branch_id,
                CampaignLead.selected,
                Campaign.deleted_at.is_(None),
            )
        )
    ).one_or_none()
    if route is None:
        raise DomainError(404, "not_found")
    member = await get_member(session, route.campaign_id, route.id, user, mutate=mutate)
    if not mutate:
        campaign = await session.get(Campaign, route.campaign_id)
        if campaign.status != "active":
            raise DomainError(409, "campaign_closed")
    if member.status != "locked":
        raise DomainError(409, "lead_unavailable")
    return await session.get(Lead, member.lead_id)


async def load_customer(session, lead_id):
    return await session.scalar(select(Customer).where(Customer.lead_id == lead_id))


def profile_from_customer(customer):
    return CustomerProfile.model_validate(
        {field: getattr(customer, field) for field in CustomerProfile.model_fields}
    ).model_dump(mode="json")


async def load_draft(session, lead_id):
    return await session.scalar(select(CustomerDraft).where(CustomerDraft.lead_id == lead_id))


def profile_from_lead(lead):
    return CustomerProfile(
        first_name=lead.first_name,
        last_name=lead.last_name,
        phone=lead.mobile,
        address=lead.address if lead.address and lead.address.strip() else None,
        city_id=lead.city_id,
        national_code=lead.national_code,
    ).model_dump(mode="json")


async def save_draft(session, lead, customer, user, profile):
    if customer:
        raise DomainError(409, "lead_is_customer")
    if profile.city_id:
        city = await session.get(City, profile.city_id)
        if not city or city.deleted_at or not city.is_active:
            raise DomainError(422, "invalid_city")
    draft = await load_draft(session, lead.id)
    if draft is None:
        draft = CustomerDraft(lead_id=lead.id, created_by=user.id, profile=profile_from_lead(lead))
        session.add(draft)
    draft.profile = draft.profile | profile.model_dump(mode="json", exclude_unset=True)
    draft.entered_by = user.id
    draft.updated_by = user.id
    await session.flush()
    return draft


async def sales_form(session, user, visit_id):
    lead = await visit_context(session, user, visit_id)
    customer = await load_customer(session, lead.id)
    held = []
    if customer:
        profile = profile_from_customer(customer)
        held = [
            {"id": key, "name": name}
            for key, name in await session.execute(
                select(BankingProduct.id, BankingProduct.name)
                .join(CustomerProduct, CustomerProduct.banking_product_id == BankingProduct.id)
                .where(CustomerProduct.customer_id == customer.id)
                .order_by(BankingProduct.name)
            )
        ]
    else:
        draft = await load_draft(session, lead.id)
        profile = draft.profile if draft else profile_from_lead(lead)
    drafts = await session.scalars(
        own_sales(user)
        .where(ProductSale.visit_id == visit_id, ProductSale.status == "draft")
        .order_by(ProductSale.registered_at, ProductSale.id)
    )
    return {
        "lead_id": lead.id,
        "customer_id": customer.id if customer else None,
        "customer_profile": profile,
        "held_products": held,
        "draft_sales": [SaleOut.model_validate(sale) for sale in drafts],
    }


async def save_form(session, user, visit_id, profile, request):
    lead = await visit_context(session, user, visit_id, mutate=True)
    draft = await save_draft(session, lead, await load_customer(session, lead.id), user, profile)
    record(session, user, "save_customer_draft", "customer_drafts", draft.id, request=request)
    return draft.profile


async def check_active_product(session, product_id):
    product = await session.get(BankingProduct, product_id)
    if not product or not product.is_active:
        raise DomainError(422, "inactive_product")


async def create_sale(session, user, body, request):
    lead = await visit_context(session, user, body.visit_id, mutate=True)
    customer = await load_customer(session, lead.id)
    await check_active_product(session, body.banking_product_id)
    if body.customer_profile is not None:
        draft = await save_draft(session, lead, customer, user, body.customer_profile)
        record(session, user, "save_customer_draft", "customer_drafts", draft.id, request=request)
    sale = ProductSale(
        **input_values(body, exclude={"customer_profile"}),
        lead_id=lead.id,
        customer_id=customer.id if customer else None,
        employee_id=user.id,
        registered_at=dates.now(),
        created_by=user.id,
        updated_by=user.id,
    )
    session.add(sale)
    await session.flush()
    record(session, user, "register_sale", "product_sales", sale.id, request=request)
    return sale


async def lock_sales(session, statement, ids, *, visit_id=None):
    keys = set(ids)
    references = (
        await session.execute(
            statement.with_only_columns(
                ProductSale.id, ProductSale.lead_id, ProductSale.visit_id
            ).where(ProductSale.id.in_(keys))
        )
    ).all()
    if len(references) != len(keys):
        raise DomainError(404, "not_found")
    if len(keys) != len(ids) or len({row.visit_id for row in references}) != 1:
        raise DomainError(422, "invalid_sale_selection")
    if visit_id is not None and references[0].visit_id != visit_id:
        raise DomainError(404, "not_found")
    leads = set(row.lead_id for row in references)
    await session.execute(
        select(Lead.id).where(Lead.id.in_(leads)).order_by(Lead.id).with_for_update()
    )
    return (
        await session.scalars(
            statement.where(ProductSale.id.in_(keys))
            .order_by(ProductSale.registered_at, ProductSale.id)
            .with_for_update(of=ProductSale)
        )
    ).all()


async def edit_sale(session, user, sale_id, request, body=None):
    (sale,) = await lock_sales(session, own_sales(user), [sale_id])
    if sale.status not in EDITABLE:
        raise DomainError(409, "sale_not_editable")
    if body is None:
        sale.status = "withdrawn"
    else:
        changes = validated_changes(body, {"banking_product_id", "account_number"})
        profile = changes.pop("customer_profile", None)
        if (product_id := changes.get("banking_product_id")) not in (None, sale.banking_product_id):
            await check_active_product(session, product_id)
        if profile is not None:
            lead = await session.get(Lead, sale.lead_id)
            draft = await save_draft(
                session, lead, await load_customer(session, lead.id), user, profile
            )
            record(
                session, user, "save_customer_draft", "customer_drafts", draft.id, request=request
            )
        for key, value in changes.items():
            setattr(sale, key, value)
    sale.updated_by = user.id
    await session.flush()
    record(
        session,
        user,
        "withdraw_sale" if body is None else "update_sale",
        "product_sales",
        sale.id,
        after={"status": sale.status},
        request=request,
    )
    return sale


async def submit(session, user, request, ids):
    rows = await lock_sales(session, own_sales(user), ids)
    lead_id = rows[0].lead_id
    customer = await load_customer(session, lead_id)
    profile = None
    if customer is None:
        draft = await load_draft(session, lead_id)
        if not draft or not all(
            draft.profile.get(key)
            for key in ("first_name", "last_name", "phone", "address", "city_id", "customer_code")
        ):
            raise DomainError(422, "customer_details_required")
        profile = draft.profile
        city_id = CustomerProfile.model_validate(profile).city_id
        city = await session.get(City, city_id)
        if not city or city.deleted_at or not city.is_active:
            raise DomainError(422, "invalid_city")
        if await session.scalar(
            select(Customer.id).where(Customer.customer_code == profile["customer_code"])
        ):
            raise DomainError(409, "customer_code_exists")
    now = dates.now()
    for sale in rows:
        if sale.status not in EDITABLE:
            raise DomainError(409, "sale_not_editable", details={"sale_id": str(sale.id)})
        proof = (sale.proof_text or "").strip()
        if sum(not char.isspace() for char in proof) < 5:
            raise DomainError(422, "proof_required", details={"sale_id": str(sale.id)})
        sale.resubmit_count += sale.status == "rejected"
        sale.status = "submitted"
        sale.submitted_at = sale.submitted_at or now
        sale.last_submitted_at = now
        sale.updated_by = user.id
        sale.rejection_reason = None
        sale.proof_text = proof
        sale.customer_id = customer.id if customer else None
        submission = SaleSubmission(
            sale_id=sale.id,
            revision=sale.resubmit_count + 1,
            profile=profile,
            banking_product_id=sale.banking_product_id,
            account_number=sale.account_number,
            description=sale.description,
            proof_text=proof,
            created_at=now,
            created_by=user.id,
        )
        session.add(submission)
        await session.flush()
        record(
            session,
            user,
            "submit_sale",
            "product_sales",
            sale.id,
            after={"submission_id": submission.id, "revision": submission.revision},
            request=request,
        )
    return rows


def current_submission():
    return and_(
        SaleSubmission.sale_id == ProductSale.id,
        SaleSubmission.revision == ProductSale.resubmit_count + 1,
    )


async def verification_queue(session, page):
    groups = (
        select(CampaignVisit)
        .join(ProductSale, ProductSale.visit_id == CampaignVisit.id)
        .where(ProductSale.status == "submitted")
        .group_by(CampaignVisit.id)
    )
    result = await paginate(
        session,
        groups,
        page,
        {"submitted_at": func.min(ProductSale.last_submitted_at)},
        "submitted_at",
        CampaignVisit.id,
    )
    visits = result["items"]
    batches = {visit.id: [] for visit in visits}
    rows = await session.execute(
        select(ProductSale, SaleSubmission, BankingProduct.name)
        .join(SaleSubmission, current_submission())
        .join(BankingProduct, BankingProduct.id == ProductSale.banking_product_id)
        .where(ProductSale.status == "submitted", ProductSale.visit_id.in_(batches))
        .order_by(ProductSale.last_submitted_at, ProductSale.id)
    )
    for sale, evidence, product in rows:
        batches[sale.visit_id].append(
            {
                "sale": SaleOut.model_validate(sale),
                "product_name": product,
                "submission": SaleSubmissionOut.model_validate(evidence),
            }
        )
    result["items"] = [{"visit_id": visit.id, "sales": batches[visit.id]} for visit in visits]
    return result


async def reviewed_sales(session, selection, *, visit_id=None):
    rows = await lock_sales(session, select(ProductSale), list(selection), visit_id=visit_id)
    evidence = dict(
        (
            await session.execute(
                select(SaleSubmission.sale_id, SaleSubmission)
                .join(ProductSale, current_submission())
                .where(ProductSale.id.in_(selection))
            )
        ).all()
    )
    result = []
    for sale in rows:
        submission = evidence.get(sale.id)
        if sale.status != "submitted" or not submission or submission.id != selection[sale.id]:
            raise DomainError(409, "stale_sale_review", details={"sale_id": str(sale.id)})
        result.append((sale, submission))
    return result


def add_decision(session, user, request, sale, submission, *, status, now, reason=None):
    sale.status = status
    sale.verified_at = now
    sale.verified_by = user.id
    sale.rejection_reason = reason
    sale.updated_by = user.id
    session.add(
        SaleDecision(
            submission_id=submission.id,
            status=status,
            reason=reason,
            decided_by=user.id,
            decided_at=now,
            created_by=user.id,
        )
    )
    session.add(
        Notification(
            recipient_id=sale.employee_id,
            event_type=f"verification_{status}",
            title=f"Sale {status}",
            payload={"sale_id": str(sale.id)},
            created_by=user.id,
            updated_by=user.id,
        )
    )
    record(
        session,
        user,
        f"verification_{status}",
        "product_sales",
        sale.id,
        {"status": "submitted"},
        {"status": status, "submission_id": submission.id},
        request,
    )


async def reject(session, user, request, sale_id, body):
    ((sale, submission),) = await reviewed_sales(session, {sale_id: body.submission_id})
    add_decision(
        session,
        user,
        request,
        sale,
        submission,
        status="rejected",
        now=dates.now(),
        reason=body.reason.strip(),
    )
    await session.flush()
    return sale
