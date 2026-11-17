from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from app.core.dates import JalaliDate
from app.core.deps import CurrentUser, Session, Supervisor
from app.core.pagination import PageParams
from app.features.pos import service_transactions as service
from app.schemas.pos import PosTransactionCreate, PosTransactionOut, PosTransactionUpdate

router = APIRouter(prefix="/pos", tags=["POS transactions"])


@router.get("/devices/{device_id}/transactions")
async def history(
    device_id: UUID,
    session: Session,
    user: CurrentUser,
    params: Annotated[PageParams, Depends()],
    from_date: JalaliDate | None = None,
    to_date: JalaliDate | None = None,
):
    return await service.transaction_history(session, user, device_id, params, from_date, to_date)


@router.post("/devices/{device_id}/transactions", status_code=201, response_model=PosTransactionOut)
async def create(
    device_id: UUID,
    body: PosTransactionCreate,
    request: Request,
    session: Session,
    user: Supervisor,
):
    row, _ = await service.write_transaction(session, user, device_id, body, request)
    return PosTransactionOut.model_validate(row)


@router.patch("/transactions/{transaction_id}", response_model=PosTransactionOut)
async def update(
    transaction_id: UUID,
    body: PosTransactionUpdate,
    request: Request,
    session: Session,
    user: Supervisor,
):
    return PosTransactionOut.model_validate(
        await service.update_transaction(session, user, transaction_id, body, request)
    )


@router.delete("/transactions/{transaction_id}", status_code=204)
async def delete(transaction_id: UUID, request: Request, session: Session, user: Supervisor):
    await service.update_transaction(session, user, transaction_id, request=request, delete=True)
    return Response(status_code=204)
