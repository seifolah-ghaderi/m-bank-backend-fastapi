from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.core.dates import JalaliDate
from app.core.deps import CurrentUser, Session, Supervisor
from app.core.pagination import PageParams
from app.features.pos import service_visits as service
from app.schemas.pos import (
    PosAssign,
    PosBulkAssign,
    PosCancel,
    PosComplete,
    PosCorrection,
    PosDispatch,
    PosTagCreate,
    PosTagUpdate,
)

router = APIRouter(prefix="/pos", tags=["POS visits"])


@router.post("/visits")
async def no_direct_creation(user: CurrentUser):
    from app.core.errors import DomainError

    raise DomainError(403, "forbidden")


@router.post("/visits/dispatch")
async def dispatch(body: PosDispatch, request: Request, session: Session, user: Supervisor):
    return await service.dispatch(session, user, body, request)


@router.post("/visits/bulk-assign")
async def bulk_assign(body: PosBulkAssign, request: Request, session: Session, user: CurrentUser):
    return await service.bulk_assign(session, user, body, request)


@router.get("/visits")
async def visits(
    session: Session,
    user: CurrentUser,
    params: Annotated[PageParams, Depends()],
    status: Literal["pending_assignment", "assigned", "completed", "cancelled"] | None = None,
    archived: bool | None = None,
    assigned_to: UUID | None = None,
    branch_id: UUID | None = None,
    pos_device_id: UUID | None = None,
    result: str | None = None,
    tag: str | None = None,
    overdue: bool | None = None,
    assigned_from: JalaliDate | None = None,
    assigned_to_date: JalaliDate | None = None,
    completed_from: JalaliDate | None = None,
    completed_to: JalaliDate | None = None,
    due_from: JalaliDate | None = None,
    due_to: JalaliDate | None = None,
):
    return await service.list_visits(
        session,
        user,
        params,
        status=status,
        archived=archived,
        assigned_to=assigned_to,
        branch_id=branch_id,
        pos_device_id=pos_device_id,
        result=result,
        tag=tag,
        overdue=overdue,
        assigned_from=assigned_from,
        assigned_to_date=assigned_to_date,
        completed_from=completed_from,
        completed_to=completed_to,
        due_from=due_from,
        due_to=due_to,
    )


@router.get("/visits/{visit_id}")
async def detail(visit_id: UUID, session: Session, user: CurrentUser):
    return await service.detail(session, user, visit_id)


@router.post("/visits/{visit_id}/assign")
async def assign(
    visit_id: UUID, body: PosAssign, request: Request, session: Session, user: CurrentUser
):
    return await service.assign(session, user, visit_id, body, request)


@router.post("/visits/{visit_id}/reassign")
async def reassign(
    visit_id: UUID, body: PosAssign, request: Request, session: Session, user: CurrentUser
):
    return await service.assign(session, user, visit_id, body, request, reassign=True)


@router.post("/visits/{visit_id}/cancel")
async def cancel(
    visit_id: UUID, body: PosCancel, request: Request, session: Session, user: CurrentUser
):
    return await service.cancel(session, user, visit_id, body.cancel_reason, request)


@router.post("/visits/{visit_id}/complete")
async def complete(
    visit_id: UUID, body: PosComplete, request: Request, session: Session, user: CurrentUser
):
    return await service.complete(session, user, visit_id, body, request)


@router.patch("/visits/{visit_id}")
async def correct(
    visit_id: UUID, body: PosCorrection, request: Request, session: Session, user: Supervisor
):
    return await service.complete(session, user, visit_id, body, request, correction=True)


@router.get("/tags")
async def tags(
    session: Session,
    user: CurrentUser,
    params: Annotated[PageParams, Depends()],
    include_inactive: bool = False,
):
    return await service.tags(session, user, params, include_inactive)


@router.post("/tags", status_code=201)
async def create_tag(body: PosTagCreate, request: Request, session: Session, user: Supervisor):
    return await service.save_tag(session, user, body, request)


@router.patch("/tags/{tag_id}")
async def update_tag(
    tag_id: UUID, body: PosTagUpdate, request: Request, session: Session, user: Supervisor
):
    return await service.save_tag(session, user, body, request, tag_id)
