from uuid import UUID

from fastapi import APIRouter

from app.core.deps import CurrentUser, Session
from app.features.reports import service

router = APIRouter(prefix="/pos/reports", tags=["POS reports"])


@router.get("/summary")
async def summary(session: Session, user: CurrentUser, branch_id: UUID | None = None):
    return await service.summary(session, user, branch_id)
