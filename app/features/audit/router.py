from uuid import UUID

from fastapi import APIRouter, Query

from app.core.dates import JalaliDate
from app.core.deps import Session, Supervisor
from app.core.pagination import PageParams
from app.features.audit.service import list_audit

router = APIRouter()


@router.get("/audit-logs")
async def audit_logs(
    session: Session,
    actor: Supervisor,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: str | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    actor_id: UUID | None = None,
    action: str | None = None,
    from_date: JalaliDate | None = None,
    to_date: JalaliDate | None = None,
):
    return await list_audit(
        session,
        PageParams(page=page, page_size=page_size, sort=sort),
        entity_type,
        entity_id,
        actor_id,
        action,
        from_date,
        to_date,
    )
