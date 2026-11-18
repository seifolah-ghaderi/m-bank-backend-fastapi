from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.core.deps import CurrentUser, Session
from app.core.pagination import PageParams
from app.features.marketing import customers
from app.schemas.sales import CustomerFilters, CustomerOut, CustomerUpdate

router = APIRouter(prefix="/customers", tags=["Customers"])
Page = Annotated[PageParams, Depends()]
Filters = Annotated[CustomerFilters, Depends()]


@router.get("")
async def listing(session: Session, user: CurrentUser, page: Page, filters: Filters):
    result = await customers.list_customers(session, user, page, filters)
    result["items"] = [CustomerOut.model_validate(item) for item in result["items"]]
    return result


@router.get("/{customer_id}")
async def detail(customer_id: UUID, session: Session, user: CurrentUser):
    return await customers.customer_detail(session, user, customer_id)


@router.patch("/{customer_id}")
async def patch(
    customer_id: UUID, body: CustomerUpdate, request: Request, session: Session, user: CurrentUser
) -> CustomerOut:
    return await customers.update_customer(session, user, customer_id, request, body)
