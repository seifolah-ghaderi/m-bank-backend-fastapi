from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.core.deps import CurrentUser, Session, Supervisor
from app.core.pagination import PageParams
from app.features.marketing import retention
from app.schemas.retention import (
    RetentionScheduleCreate,
    RetentionScheduleOut,
    RetentionScheduleUpdate,
    RetentionTaskComplete,
    RetentionTaskListItem,
    RetentionTaskOut,
    RetentionTaskStatus,
)

router = APIRouter(prefix="/retention-schedules", tags=["Retention schedules"])
tasks_router = APIRouter(prefix="/retention-tasks", tags=["Retention tasks"])
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


@tasks_router.get("")
async def task_list(
    session: Session, user: CurrentUser, page: Page, status: RetentionTaskStatus | None = None
):
    result = await retention.list_tasks(session, user, page, status)
    result["items"] = [RetentionTaskListItem.model_validate(item) for item in result["items"]]
    return result


@tasks_router.get("/{task_id}")
async def task_detail(task_id: UUID, session: Session, user: CurrentUser) -> RetentionTaskOut:
    return await retention.task_detail(session, user, task_id)


@tasks_router.post("/{task_id}/complete")
async def complete(
    task_id: UUID,
    body: RetentionTaskComplete,
    request: Request,
    session: Session,
    user: CurrentUser,
) -> RetentionTaskOut:
    return await retention.complete_task(session, user, task_id, body, request)
