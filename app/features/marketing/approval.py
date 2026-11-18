from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core import dates
from app.core.audit import record
from app.core.errors import DomainError
from app.features.marketing.retention import generate_tasks
from app.features.marketing.sales import add_decision, load_customer, reviewed_sales
from app.models import (
    BankingProduct,
    Customer,
    CustomerProduct,
    Lead,
    ProductSale,
    SaleSubmission,
    ScoreTransaction,
)
from app.schemas.sales import CustomerProfile


async def approve(session, actor, request, selection, *, visit_id=None):
    claims = await reviewed_sales(session, selection, visit_id=visit_id)
    first_sale, first_submission = claims[0]
    lead = await session.get(Lead, first_sale.lead_id)
    customer = await load_customer(session, lead.id)
    converting = customer is None
    if converting:
        converted_profile = first_submission.profile
    else:
        converted_profile = await session.scalar(
            select(SaleSubmission.profile)
            .join(ProductSale, ProductSale.id == SaleSubmission.sale_id)
            .where(
                ProductSale.id == customer.first_sale_id,
                SaleSubmission.revision == ProductSale.resubmit_count + 1,
            )
        )
    for sale, submission in claims:
        if (
            converting
            and submission.profile is None
            or (submission.profile is not None and submission.profile != converted_profile)
        ):
            raise DomainError(
                409, "conflicting_customer_profile", details={"sale_id": str(sale.id)}
            )
        if sale.customer_id is not None and (converting or sale.customer_id != customer.id):
            raise DomainError(
                409, "conflicting_customer_profile", details={"sale_id": str(sale.id)}
            )

    product_ids = {submission.banking_product_id for _, submission in claims}
    products = {
        product.id: product
        for product in await session.scalars(
            select(BankingProduct)
            .where(BankingProduct.id.in_(product_ids))
            .order_by(BankingProduct.id)
            .with_for_update(read=True)
        )
    }
    if not converting and await session.scalar(
        select(CustomerProduct.id)
        .where(
            CustomerProduct.customer_id == customer.id,
            CustomerProduct.banking_product_id.in_(product_ids),
        )
        .limit(1)
    ):
        raise DomainError(409, "product_already_held")

    now = dates.now()
    approval_date = now.astimezone(ZoneInfo(dates.business_timezone.get())).date()
    if converting:
        profile = CustomerProfile.model_validate(converted_profile)
        customer = Customer(
            **profile.model_dump(),
            lead_id=lead.id,
            branch_id=lead.branch_id,
            acquired_by=first_sale.employee_id,
            first_sale_id=first_sale.id,
            customer_since=approval_date,
            converted_at=now,
            created_by=actor.id,
            updated_by=actor.id,
        )
        session.add(customer)
        lead.is_customer = True
        lead.updated_by = actor.id
        await session.flush()
        await generate_tasks(session, customer, actor)
        record(
            session,
            actor,
            "convert_lead",
            "customers",
            customer.id,
            after={"lead_id": lead.id, "first_sale_id": first_sale.id},
            request=request,
        )

    for sale, submission in claims:
        sale.customer_id = customer.id
        product_id = submission.banking_product_id
        session.add(
            CustomerProduct(
                customer_id=customer.id,
                banking_product_id=product_id,
                source_sale_id=sale.id,
                account_number=submission.account_number,
                started_at=approval_date,
                created_by=actor.id,
                updated_by=actor.id,
            )
        )
        session.add(
            ScoreTransaction(
                employee_id=sale.employee_id,
                source_type="product_sale",
                source_id=sale.id,
                points=products[product_id].score_value,
                occurred_at=now,
                created_by=actor.id,
                updated_by=actor.id,
            )
        )
        add_decision(session, actor, request, sale, submission, status="approved", now=now)
    await session.flush()
    return customer, [sale for sale, _ in claims]
