from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from app.core.deps import CurrentUser, Session, Supervisor
from app.core.pagination import PageParams
from app.features.org import service
from app.models import Branch, City
from app.schemas.org import BranchCreate, BranchOut, BranchUpdate, CityCreate, CityOut, CityUpdate

router = APIRouter()


@router.get("/cities")
async def cities(
    session: Session,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: str | None = None,
    q: str | None = None,
    include_inactive: bool | None = None,
    is_active: bool | None = None,
):
    return await service.list_entities(
        session,
        City,
        user,
        PageParams(page=page, page_size=page_size, sort=sort),
        q,
        include_inactive,
        is_active,
    )


@router.post("/cities", status_code=201, response_model=CityOut)
async def create_city(body: CityCreate, request: Request, session: Session, user: Supervisor):
    return await service.create_entity(session, City, body, user, request)


@router.get("/cities/{entity_id}", response_model=CityOut)
async def city(entity_id: UUID, session: Session, user: CurrentUser):
    return await service.get_entity(session, City, entity_id, user)


@router.patch("/cities/{entity_id}", response_model=CityOut)
async def update_city(
    entity_id: UUID, body: CityUpdate, request: Request, session: Session, user: Supervisor
):
    return await service.update_entity(session, City, entity_id, body, user, request)


@router.delete("/cities/{entity_id}", status_code=204)
async def delete_city(entity_id: UUID, request: Request, session: Session, user: Supervisor):
    await service.delete_entity(session, City, entity_id, user, request)
    return Response(status_code=204)


@router.get("/branches")
async def branches(
    session: Session,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: str | None = None,
    q: str | None = None,
    include_inactive: bool | None = None,
    is_active: bool | None = None,
    branch_id: UUID | None = None,
    city_id: UUID | None = None,
):
    return await service.list_entities(
        session,
        Branch,
        user,
        PageParams(page=page, page_size=page_size, sort=sort),
        q,
        include_inactive,
        is_active,
        branch_id,
        city_id,
    )


@router.post("/branches", status_code=201, response_model=BranchOut)
async def create_branch(body: BranchCreate, request: Request, session: Session, user: Supervisor):
    return await service.create_entity(session, Branch, body, user, request)


@router.get("/branches/{entity_id}", response_model=BranchOut)
async def branch(entity_id: UUID, session: Session, user: CurrentUser):
    return await service.branch_out(
        session, await service.get_entity(session, Branch, entity_id, user)
    )


@router.patch("/branches/{entity_id}", response_model=BranchOut)
async def update_branch(
    entity_id: UUID, body: BranchUpdate, request: Request, session: Session, user: Supervisor
):
    return await service.update_entity(session, Branch, entity_id, body, user, request)


@router.delete("/branches/{entity_id}", status_code=204)
async def delete_branch(entity_id: UUID, request: Request, session: Session, user: Supervisor):
    await service.delete_entity(session, Branch, entity_id, user, request)
    return Response(status_code=204)
