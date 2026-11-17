from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.core.deps import CurrentUser, Session, Supervisor
from app.core.pagination import PageParams
from app.features.pos import productivity, service_settings
from app.schemas.pos import PerformanceSettingsOut, PerformanceSettingsUpdate, PeriodInput, Status

router = APIRouter(prefix="/pos", tags=["POS performance"])


@router.get("/performance-settings", response_model=PerformanceSettingsOut)
async def settings(session: Session, user: CurrentUser):
    return PerformanceSettingsOut.model_validate(await service_settings.get_settings(session, user))


@router.patch("/performance-settings", response_model=PerformanceSettingsOut)
async def update(
    body: PerformanceSettingsUpdate, request: Request, session: Session, user: Supervisor
):
    return PerformanceSettingsOut.model_validate(
        await service_settings.update_settings(session, user, body, request)
    )


@router.get("/productivity")
async def ranking(
    session: Session,
    user: CurrentUser,
    period: Annotated[PeriodInput, Depends()],
    params: Annotated[PageParams, Depends()],
    performance: Literal["low", "normal", "high"] | None = None,
    no_data: bool | None = None,
    branch_id: UUID | None = None,
    city_id: UUID | None = None,
    status: Status | None = None,
):
    return await productivity.ranking(
        session,
        user,
        period,
        params,
        performance=performance,
        no_data=no_data,
        branch_id=branch_id,
        city_id=city_id,
        status=status,
    )


@router.get("/devices/{device_id}/productivity")
async def per_device(
    device_id: UUID, session: Session, user: CurrentUser, period: Annotated[PeriodInput, Depends()]
):
    return await productivity.device_performance(session, user, device_id, period)
