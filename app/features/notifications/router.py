from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from app.core.deps import CurrentUser, Session
from app.core.pagination import PageParams
from app.features.notifications import service
from app.schemas.notifications import NotificationOut

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
async def notifications(
    session: Session,
    user: CurrentUser,
    params: Annotated[PageParams, Depends()],
    is_read: bool | None = None,
):
    return await service.notifications(session, user, params, is_read)


@router.get("/unread-count")
async def unread(session: Session, user: CurrentUser):
    return await service.unread_count(session, user)


@router.post("/read-all", status_code=204)
async def read_all(session: Session, user: CurrentUser):
    await service.mark_read(session, user)
    return Response(status_code=204)


@router.get("/{notification_id}", response_model=NotificationOut)
async def notification(notification_id: UUID, session: Session, user: CurrentUser):
    return NotificationOut.model_validate(
        await service.get_notification(session, user, notification_id)
    )


@router.post("/{notification_id}/read", status_code=204)
async def read(notification_id: UUID, session: Session, user: CurrentUser):
    await service.mark_read(session, user, notification_id)
    return Response(status_code=204)
