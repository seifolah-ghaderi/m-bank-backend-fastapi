from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.core.deps import CurrentUser, Session, Supervisor
from app.core.errors import DomainError
from app.core.pagination import PageParams
from app.features.marketing import approval, sales
from app.schemas.sales import (
    BatchApproval,
    CustomerOut,
    CustomerProfile,
    RejectSale,
    ReviewSelection,
    SaleCreate,
    SaleOut,
    SaleUpdate,
    SubmitSales,
)

router = APIRouter(tags=["Sales"])
Page = Annotated[PageParams, Depends()]


@router.get("/visits/{visit_id}/sales-form")
async def sales_form(visit_id: UUID, session: Session, user: CurrentUser):
    return await sales.sales_form(session, user, visit_id)


@router.patch("/visits/{visit_id}/sales-form")
async def save_form(
    visit_id: UUID, body: CustomerProfile, request: Request, session: Session, user: CurrentUser
) -> CustomerProfile:
    return await sales.save_form(session, user, visit_id, body, request)


@router.post("/sales", status_code=201)
async def create_sale(
    body: SaleCreate, request: Request, session: Session, user: CurrentUser
) -> SaleOut:
    return await sales.create_sale(session, user, body, request)


@router.get("/sales")
async def list_sales(
    session: Session,
    user: CurrentUser,
    page: Page,
    status: Literal["draft", "submitted", "approved", "rejected", "withdrawn"] | None = None,
):
    result = await sales.sale_list(session, user, page, status)
    result["items"] = [SaleOut.model_validate(sale) for sale in result["items"]]
    return result


@router.post("/sales/submit")
async def submit(
    body: SubmitSales, request: Request, session: Session, user: CurrentUser
) -> list[SaleOut]:
    return await sales.submit(session, user, request, body.sale_ids)


@router.get("/sales/{sale_id}")
async def get_sale(sale_id: UUID, session: Session, user: CurrentUser) -> SaleOut:
    return await sales.sale_detail(session, user, sale_id)


@router.patch("/sales/{sale_id}")
async def edit_sale(
    sale_id: UUID, body: SaleUpdate, request: Request, session: Session, user: CurrentUser
) -> SaleOut:
    return await sales.edit_sale(session, user, sale_id, request, body)


@router.post("/sales/{sale_id}/withdraw")
async def withdraw(sale_id: UUID, request: Request, session: Session, user: CurrentUser) -> SaleOut:
    return await sales.edit_sale(session, user, sale_id, request)


@router.get("/verifications")
async def queue(session: Session, user: Supervisor, page: Page):
    return await sales.verification_queue(session, page)


@router.post("/sales/{sale_id}/reject")
async def reject(
    sale_id: UUID, body: RejectSale, request: Request, session: Session, user: Supervisor
) -> SaleOut:
    return await sales.reject(session, user, request, sale_id, body)


@router.post("/sales/{sale_id}/approve")
async def approve_one(
    sale_id: UUID, body: ReviewSelection, request: Request, session: Session, user: Supervisor
):
    customer, approved = await approval.approve(
        session, user, request, {sale_id: body.submission_id}
    )
    return {
        "customer": CustomerOut.model_validate(customer),
        "sales": [SaleOut.model_validate(sale) for sale in approved],
    }


@router.post("/verifications/visits/{visit_id}/approve")
async def approve_batch(
    visit_id: UUID, body: BatchApproval, request: Request, session: Session, user: Supervisor
):
    selection = {item.sale_id: item.submission_id for item in body.sales}
    if len(selection) != len(body.sales):
        raise DomainError(422, "invalid_sale_selection")
    customer, approved = await approval.approve(
        session, user, request, selection, visit_id=visit_id
    )
    return {
        "customer": CustomerOut.model_validate(customer),
        "sales": [SaleOut.model_validate(sale) for sale in approved],
    }
