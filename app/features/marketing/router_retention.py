from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.core.deps import Session, Supervisor
from app.core.pagination import PageParams
from app.features.marketing import retention
from app.schemas.retention import (
    RetentionScheduleCreate,
    RetentionScheduleOut,
    RetentionScheduleUpdate,
)

router = APIRouter(prefix="/retention-schedules", tags=["Retention schedules"])
Page = Annotated[PageParams, Depends()]


@router.get("")
async def listing(session: Session, user: Supervisor, page: Page, include_inactive: bool = False):
    result = await retention.list_schedules(session, page, include_inactive)
    result["items"] = [RetentionScheduleOut.model_validate(item) for item in result["items"]]
    return result


@router.post("", status_code=201)
async def create(
    body: RetentionScheduleCreate, request: Request, session: Session, user: Supervisor
) -> RetentionScheduleOut:
    return await retention.save_schedule(session, user, request, body)


@router.patch("/{schedule_id}")
async def patch(
    schedule_id: UUID,
    body: RetentionScheduleUpdate,
    request: Request,
    session: Session,
    user: Supervisor,
) -> RetentionScheduleOut:
    return await retention.save_schedule(session, user, request, body, schedule_id)
