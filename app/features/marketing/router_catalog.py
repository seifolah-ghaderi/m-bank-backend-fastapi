from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.core.deps import CurrentUser, Session, Supervisor
from app.core.pagination import PageParams
from app.features.marketing import catalog
from app.models import BankingProduct, Occupation
from app.schemas.marketing import (
    BankingProductCreate,
    BankingProductOut,
    BankingProductUpdate,
    OccupationCreate,
    OccupationOut,
    OccupationUpdate,
)

router = APIRouter(tags=["Sales catalog"])
Page = Annotated[PageParams, Depends()]


@router.get("/occupations")
async def occupations(
    session: Session, user: CurrentUser, page: Page, include_inactive: bool = False
):
    result = await catalog.list_entries(session, Occupation, user, page, include_inactive)
    result["items"] = [OccupationOut.model_validate(item) for item in result["items"]]
    return result


@router.post("/occupations", status_code=201)
async def create_occupation(
    body: OccupationCreate, request: Request, session: Session, user: Supervisor
) -> OccupationOut:
    return await catalog.save(session, Occupation, body, user, request)


@router.patch("/occupations/{entry_id}")
async def update_occupation(
    entry_id: UUID, body: OccupationUpdate, request: Request, session: Session, user: Supervisor
) -> OccupationOut:
    return await catalog.save(session, Occupation, body, user, request, entry_id)


@router.get("/banking-products")
async def products(session: Session, user: CurrentUser, page: Page, include_inactive: bool = False):
    result = await catalog.list_entries(session, BankingProduct, user, page, include_inactive)
    result["items"] = [BankingProductOut.model_validate(item) for item in result["items"]]
    return result


@router.post("/banking-products", status_code=201)
async def create_product(
    body: BankingProductCreate, request: Request, session: Session, user: Supervisor
) -> BankingProductOut:
    return await catalog.save(session, BankingProduct, body, user, request)


@router.patch("/banking-products/{entry_id}")
async def update_product(
    entry_id: UUID, body: BankingProductUpdate, request: Request, session: Session, user: Supervisor
) -> BankingProductOut:
    return await catalog.save(session, BankingProduct, body, user, request, entry_id)
