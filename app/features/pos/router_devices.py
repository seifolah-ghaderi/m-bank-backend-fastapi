from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from app.core.dates import JalaliDate
from app.core.deps import CurrentUser, Session, Supervisor
from app.core.pagination import PageParams
from app.features.pos import service_devices as service
from app.schemas.pos import (
    PosDeviceCreate,
    PosDeviceDetail,
    PosDeviceOut,
    PosDeviceUpdate,
    PosOwnerChange,
    PosTransfer,
    Status,
)

router = APIRouter(prefix="/pos/devices", tags=["POS registry"])
Pages = Annotated[PageParams, Depends()]


@router.get("")
async def devices(
    session: Session,
    user: CurrentUser,
    params: Pages,
    q: str | None = None,
    branch_id: UUID | None = None,
    city_id: UUID | None = None,
    status: Status | None = None,
    source: str | None = None,
    has_open_visit: bool | None = None,
    no_transactions_since: JalaliDate | None = None,
    include_deleted: bool = False,
):
    return await service.list_devices(
        session,
        user,
        params,
        q=q,
        branch_id=branch_id,
        city_id=city_id,
        status=status,
        source=source,
        has_open_visit=has_open_visit,
        no_transactions_since=no_transactions_since,
        include_deleted=include_deleted,
    )


@router.post("", status_code=201, response_model=PosDeviceOut)
async def create(body: PosDeviceCreate, request: Request, session: Session, user: Supervisor):
    return PosDeviceOut.model_validate(await service.create_device(session, user, body, request))


@router.get("/export")
async def export(
    session: Session,
    user: CurrentUser,
    q: str | None = None,
    branch_id: UUID | None = None,
    city_id: UUID | None = None,
    status: Status | None = None,
    source: str | None = None,
    has_open_visit: bool | None = None,
    no_transactions_since: JalaliDate | None = None,
    include_deleted: bool = False,
):
    from app.core.excel import xlsx_response

    content = await service.export_devices(
        session,
        user,
        q=q,
        branch_id=branch_id,
        city_id=city_id,
        status=status,
        source=source,
        has_open_visit=has_open_visit,
        no_transactions_since=no_transactions_since,
        include_deleted=include_deleted,
    )
    return xlsx_response(content, "pos-devices.xlsx")


@router.get("/{device_id}", response_model=PosDeviceDetail)
async def device(
    device_id: UUID, session: Session, user: CurrentUser, include_deleted: bool = False
):
    return await service.detail(session, user, device_id, include_deleted=include_deleted)


@router.patch("/{device_id}", response_model=PosDeviceOut)
async def update(
    device_id: UUID, body: PosDeviceUpdate, request: Request, session: Session, user: Supervisor
):
    return PosDeviceOut.model_validate(
        await service.update_device(session, user, device_id, body, request)
    )


@router.delete("/{device_id}", status_code=204)
async def delete(device_id: UUID, request: Request, session: Session, user: Supervisor):
    await service.delete_restore(session, user, device_id, request)
    return Response(status_code=204)


@router.post("/{device_id}/restore", response_model=PosDeviceOut)
async def restore(device_id: UUID, request: Request, session: Session, user: Supervisor):
    return PosDeviceOut.model_validate(
        await service.delete_restore(session, user, device_id, request, restore=True)
    )


@router.post("/{device_id}/transfer", response_model=PosDeviceOut)
async def transfer(
    device_id: UUID, body: PosTransfer, request: Request, session: Session, user: Supervisor
):
    return PosDeviceOut.model_validate(
        await service.transfer(session, user, device_id, body, request)
    )


@router.post("/{device_id}/change-owner", response_model=PosDeviceOut)
async def owner(
    device_id: UUID, body: PosOwnerChange, request: Request, session: Session, user: Supervisor
):
    return PosDeviceOut.model_validate(
        await service.change_owner(session, user, device_id, body, request)
    )


@router.get("/{device_id}/branch-history")
async def branch_history(device_id: UUID, session: Session, user: CurrentUser, params: Pages):
    return await service.history(session, user, device_id, "branch", params)


@router.get("/{device_id}/owner-history")
async def owner_history(device_id: UUID, session: Session, user: CurrentUser, params: Pages):
    return await service.history(session, user, device_id, "owner", params)
