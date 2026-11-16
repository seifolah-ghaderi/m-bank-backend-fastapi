from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from app.core.deps import CurrentUser, Session, Supervisor
from app.core.pagination import PageParams
from app.features.users import service
from app.schemas.users import Role, UserCreate, UserCreated, UserOut, UserUpdate

router = APIRouter(prefix="/users")


@router.get("")
async def users(
    session: Session,
    actor: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: str | None = None,
    branch_id: UUID | None = None,
    city_id: UUID | None = None,
    role: Role | None = None,
    is_active: bool | None = None,
    q: str | None = None,
):
    return await service.list_users(
        session,
        actor,
        PageParams(page=page, page_size=page_size, sort=sort),
        branch_id,
        city_id,
        role,
        is_active,
        q,
    )


@router.post("", status_code=201, response_model=UserCreated)
async def create_user(body: UserCreate, request: Request, session: Session, actor: Supervisor):
    return await service.create_user(session, body, actor, request)


@router.get("/{user_id}", response_model=UserOut)
async def user(user_id: UUID, session: Session, actor: CurrentUser):
    return await service.get_user(session, user_id, actor)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: UUID, body: UserUpdate, request: Request, session: Session, actor: Supervisor
):
    return await service.update_user(session, user_id, actor, request, body)


@router.post("/{user_id}/activate", response_model=UserOut)
async def activate(user_id: UUID, request: Request, session: Session, actor: Supervisor):
    return await service.update_user(session, user_id, actor, request, action="activate")


@router.post("/{user_id}/deactivate", response_model=UserOut)
async def deactivate(user_id: UUID, request: Request, session: Session, actor: Supervisor):
    return await service.update_user(session, user_id, actor, request, action="deactivate")


@router.post("/{user_id}/reset-password", response_model=UserCreated)
async def reset(user_id: UUID, request: Request, session: Session, actor: Supervisor):
    return await service.update_user(session, user_id, actor, request, action="reset_password")


@router.delete("/{user_id}", status_code=204)
async def delete(user_id: UUID, request: Request, session: Session, actor: Supervisor):
    await service.update_user(session, user_id, actor, request, action="delete")
    return Response(status_code=204)
