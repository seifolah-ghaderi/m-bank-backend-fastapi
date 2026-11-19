from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.core.deps import Session, Supervisor
from app.core.pagination import PageParams
from app.features.marketing import leads
from app.schemas.marketing import LeadBranchAssignment, LeadCreate, LeadFilters, LeadOut

router = APIRouter(prefix="/leads", tags=["Leads"])
Page = Annotated[PageParams, Depends()]
Filters = Annotated[LeadFilters, Depends()]


@router.get("")
async def list_leads(
    session: Session,
    user: Supervisor,
    page: Page,
    filters: Filters,
    include_archived: bool = False,
    archived: bool | None = None,
    unassigned: bool = False,
):
    result = await leads.list_leads(
        session, page, filters, include_archived, archived, unassigned=unassigned
    )
    result["items"] = [LeadOut.model_validate(item) for item in result["items"]]
    return result


@router.get("/{lead_id}")
async def get_lead(lead_id: UUID, session: Session, user: Supervisor) -> LeadOut:
    return await leads.get_lead(session, lead_id)


@router.post("", status_code=201)
async def create_lead(
    body: LeadCreate, request: Request, session: Session, user: Supervisor
) -> LeadOut:
    return await leads.create_lead(session, body, user, request)


@router.post("/{lead_id}/archive")
async def archive(lead_id: UUID, request: Request, session: Session, user: Supervisor) -> LeadOut:
    return await leads.archive_lead(session, lead_id, user, request, archive=True)


@router.post("/{lead_id}/restore")
async def restore(lead_id: UUID, request: Request, session: Session, user: Supervisor) -> LeadOut:
    return await leads.archive_lead(session, lead_id, user, request, archive=False)


@router.post("/{lead_id}/assign-branch")
async def assign_branch(
    lead_id: UUID, body: LeadBranchAssignment, request: Request, session: Session, user: Supervisor
) -> LeadOut:
    return await leads.assign_branch(session, lead_id, body.branch_id, user, request)
