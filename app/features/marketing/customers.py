from sqlalchemy import func, or_, select

from app.core import dates
from app.core.audit import record
from app.core.deps import require_roles, scope_for
from app.core.errors import DomainError
from app.core.pagination import paginate
from app.core.text import normalize_text
from app.core.validation import validated_changes
from app.models import (
    BankingProduct,
    Campaign,
    CampaignLead,
    CampaignVisit,
    City,
    Customer,
    CustomerProduct,
    ProductSale,
    RetentionSchedule,
    RetentionTask,
    VisitAttempt,
)
from app.schemas.campaigns import VisitAttemptOut, VisitOut
from app.schemas.sales import CustomerOut


def scoped_customers(user):
    require_roles(user, "supervisor", "branch_manager")
    return scope_for(user).apply(select(Customer), Customer)


async def list_customers(session, user, page, filters):
    statement = scoped_customers(user)
    if filters.branch_id is not None:
        if user.role == "branch_manager" and filters.branch_id != user.branch_id:
            raise DomainError(403, "forbidden")
        statement = statement.where(Customer.branch_id == filters.branch_id)
    if filters.city_id is not None:
        statement = statement.where(Customer.city_id == filters.city_id)
    if filters.product_id is not None:
        held = select(CustomerProduct.id).where(
            CustomerProduct.customer_id == Customer.id,
            CustomerProduct.banking_product_id == filters.product_id,
        )
        statement = statement.where(held.exists())
    if filters.customer_since_from is not None:
        statement = statement.where(Customer.customer_since >= filters.customer_since_from)
    if filters.customer_since_to is not None:
        statement = statement.where(Customer.customer_since <= filters.customer_since_to)
    if (
        filters.customer_since_from
        and filters.customer_since_to
        and filters.customer_since_from > filters.customer_since_to
    ):
        raise DomainError(422, "invalid_date_range")
    if filters.q and (query := normalize_text(filters.q).lower()):
        name = func.lower(Customer.first_name + " " + Customer.last_name)
        statement = statement.where(
            or_(
                name.contains(query, autoescape=True),
                Customer.phone.contains(query, autoescape=True),
            )
        )
    return await paginate(
        session,
        statement,
        page,
        {"name": Customer.last_name, "customer_since": Customer.customer_since},
        "-customer_since",
        Customer.id,
    )


async def get_customer(session, user, customer_id, *, lock=False):
    statement = scoped_customers(user).where(Customer.id == customer_id)
    if lock:
        statement = statement.with_for_update()
    customer = await session.scalar(statement)
    if customer is None:
        raise DomainError(404, "not_found")
    return customer


async def customer_detail(session, user, customer_id):
    customer = await get_customer(session, user, customer_id)
    products = await session.execute(
        select(CustomerProduct, BankingProduct.name)
        .join(BankingProduct, BankingProduct.id == CustomerProduct.banking_product_id)
        .where(CustomerProduct.customer_id == customer.id)
        .order_by(CustomerProduct.started_at, CustomerProduct.id)
    )
    supervisor = user.role == "supervisor"
    product_rows = [
        {
            "id": item.id,
            "banking_product_id": item.banking_product_id,
            "name": name,
            "started_at": dates.format_date(item.started_at),
            "source_sale_id": item.source_sale_id,
            **({"account_number": item.account_number} if supervisor else {}),
        }
        for item, name in products
    ]
    claims = await session.scalars(
        select(ProductSale)
        .where(
            ProductSale.lead_id == customer.lead_id,
        )
        .order_by(ProductSale.registered_at, ProductSale.id)
    )
    sale_rows = [
        {
            "id": item.id,
            "visit_id": item.visit_id,
            "employee_id": item.employee_id,
            "banking_product_id": item.banking_product_id,
            "status": item.status,
            "registered_at": dates.format_datetime(item.registered_at),
        }
        for item in claims
    ]
    visits = (
        await session.execute(
            select(CampaignVisit, Campaign.title)
            .join(CampaignLead, CampaignLead.id == CampaignVisit.campaign_lead_id)
            .join(Campaign, Campaign.id == CampaignLead.campaign_id)
            .where(CampaignLead.lead_id == customer.lead_id)
            .order_by(CampaignVisit.created_at, CampaignVisit.id)
        )
    ).all()
    attempts = {visit.id: [] for visit, _ in visits}
    for attempt in await session.scalars(
        select(VisitAttempt)
        .where(VisitAttempt.visit_id.in_(attempts))
        .order_by(VisitAttempt.attempt_no)
    ):
        attempts[attempt.visit_id].append(VisitAttemptOut.model_validate(attempt))
    visit_rows = [
        {
            "visit": VisitOut.model_validate(visit),
            "campaign_title": title,
            "attempts": attempts[visit.id],
        }
        for visit, title in visits
    ]
    tasks = await session.execute(
        select(RetentionTask, RetentionSchedule.label)
        .join(RetentionSchedule, RetentionSchedule.id == RetentionTask.retention_schedule_id)
        .where(RetentionTask.customer_id == customer.id)
        .order_by(RetentionTask.due_date, RetentionTask.id)
    )
    task_rows = [
        {
            "id": task.id,
            "schedule_id": task.retention_schedule_id,
            "label": label,
            "due_date": dates.format_date(task.due_date),
            "assigned_to": task.assigned_to,
            "status": task.status,
        }
        for task, label in tasks
    ]
    return {
        "customer": CustomerOut.model_validate(customer),
        "products": product_rows,
        "sales": sale_rows,
        "visits": visit_rows,
        "retention_tasks": task_rows,
    }


async def update_customer(session, user, customer_id, request, body):
    customer = await get_customer(session, user, customer_id, lock=True)
    changes = validated_changes(body, type(body).model_fields)
    if city_id := changes.get("city_id"):
        city = await session.get(City, city_id)
        if not city or city.deleted_at or not city.is_active:
            raise DomainError(422, "invalid_city")
    changed = []
    for key, value in changes.items():
        if value != getattr(customer, key):
            setattr(customer, key, value)
            changed.append(key)
    if changed:
        customer.updated_by = user.id
        record(
            session,
            user,
            "update_contact",
            "customers",
            customer.id,
            after={"fields": sorted(changed)},
            request=request,
        )
        await session.flush()
    return customer
