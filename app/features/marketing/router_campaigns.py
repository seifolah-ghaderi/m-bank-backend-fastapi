from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from app.core.deps import CurrentUser, Session, Supervisor
from app.core.pagination import PageParams
from app.features.marketing import campaigns, work
from app.schemas.campaigns import (
    CampaignCreate,
    CampaignLeadOut,
    CampaignOut,
    CampaignUpdate,
    QuotaOverrideUpdate,
    Reassignment,
    SelectionChange,
    VisitAttemptOut,
    VisitCreate,
    VisitOut,
)
from app.schemas.marketing import LeadFilters, LeadOut

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])
Page = Annotated[PageParams, Depends()]
Filters = Annotated[LeadFilters, Depends()]


@router.post("", status_code=201)
async def create(
    body: CampaignCreate, request: Request, session: Session, user: Supervisor
) -> CampaignOut:
    return await campaigns.save_campaign(session, user, request, body)


@router.get("")
async def listing(
    session: Session,
    user: CurrentUser,
    page: Page,
    status: Literal["draft", "active", "closed"] | None = None,
):
    result = await campaigns.list_campaigns(session, user, page, status)
    result["items"] = [CampaignOut.model_validate(item) for item in result["items"]]
    return result


@router.get("/{campaign_id}")
async def detail(campaign_id: UUID, session: Session, user: CurrentUser) -> CampaignOut:
    return await campaigns.get_campaign(session, campaign_id, user)


@router.patch("/{campaign_id}")
async def patch(
    campaign_id: UUID, body: CampaignUpdate, request: Request, session: Session, user: Supervisor
) -> CampaignOut:
    return await campaigns.save_campaign(session, user, request, body, campaign_id)


@router.delete("/{campaign_id}", status_code=204)
async def delete(
    campaign_id: UUID, request: Request, session: Session, user: Supervisor
) -> Response:
    await campaigns.delete_campaign(session, campaign_id, user, request)
    return Response(status_code=204)


@router.get("/{campaign_id}/selection/preview")
async def preview(
    campaign_id: UUID, session: Session, user: Supervisor, page: Page, filters: Filters
):
    result = await campaigns.preview(session, campaign_id, user, page, filters)
    result["items"] = [LeadOut.model_validate(item) for item in result["items"]]
    return result


@router.post("/{campaign_id}/selection")
async def select_leads(
    campaign_id: UUID, body: SelectionChange, request: Request, session: Session, user: Supervisor
):
    return await campaigns.change_selection(session, campaign_id, user, request, body)


@router.post("/{campaign_id}/activate")
async def activate(campaign_id: UUID, request: Request, session: Session, user: Supervisor):
    campaign, empty = await campaigns.transition(session, campaign_id, user, request, activate=True)
    return {"campaign": CampaignOut.model_validate(campaign), "branches_without_staff": empty}


@router.post("/{campaign_id}/close")
async def close(
    campaign_id: UUID, request: Request, session: Session, user: Supervisor
) -> CampaignOut:
    campaign, _ = await campaigns.transition(session, campaign_id, user, request, activate=False)
    return campaign


@router.get("/{campaign_id}/leads")
async def list_work(campaign_id: UUID, session: Session, user: CurrentUser, page: Page):
    result, leads, held = await work.list_work(session, campaign_id, user, page)
    result["items"] = [
        CampaignLeadOut.model_validate(item).model_dump(mode="json")
        | {
            "first_name": leads[item.lead_id].first_name,
            "last_name": leads[item.lead_id].last_name,
            "is_customer": leads[item.lead_id].is_customer,
            "held_products": held.get(item.lead_id, []),
            "mobile": leads[item.lead_id].mobile if item.locked_by == user.id else None,
            "address": leads[item.lead_id].address if item.locked_by == user.id else None,
        }
        for item in result["items"]
    ]
    return result


@router.post("/{campaign_id}/leads/{membership_id}/pick")
async def pick(
    campaign_id: UUID, membership_id: UUID, request: Request, session: Session, user: CurrentUser
) -> CampaignLeadOut:
    return await work.assign(session, campaign_id, membership_id, user, request)


@router.post("/{campaign_id}/leads/{membership_id}/reassign")
async def reassign(
    campaign_id: UUID,
    membership_id: UUID,
    body: Reassignment,
    request: Request,
    session: Session,
    user: CurrentUser,
) -> CampaignLeadOut:
    return await work.assign(
        session, campaign_id, membership_id, user, request, employee_id=body.employee_id
    )


@router.get("/{campaign_id}/branches/{branch_id}/capacity")
async def capacity(campaign_id: UUID, branch_id: UUID, session: Session, user: CurrentUser):
    items = await work.branch_capacity(session, campaign_id, branch_id, user)
    return {"items": items}


@router.patch("/{campaign_id}/branches/{branch_id}/capacity/{employee_id}")
async def override(
    campaign_id: UUID,
    branch_id: UUID,
    employee_id: UUID,
    body: QuotaOverrideUpdate,
    request: Request,
    session: Session,
    user: CurrentUser,
):
    return await work.override(session, campaign_id, branch_id, employee_id, user, request, body)


@router.post("/{campaign_id}/leads/{membership_id}/visits", status_code=201)
async def record_visit(
    campaign_id: UUID,
    membership_id: UUID,
    body: VisitCreate,
    request: Request,
    session: Session,
    user: CurrentUser,
) -> VisitOut:
    return await work.append_visit(session, campaign_id, membership_id, user, request, body)


@router.get("/{campaign_id}/leads/{membership_id}/visits")
async def visit_history(
    campaign_id: UUID, membership_id: UUID, session: Session, user: CurrentUser, page: Page
):
    visit, attempts = await work.visit_history(session, campaign_id, membership_id, user, page)
    attempts["items"] = [VisitAttemptOut.model_validate(item) for item in attempts["items"]]
    return {"visit": VisitOut.model_validate(visit), "attempts": attempts}


@router.post("/{campaign_id}/leads/{membership_id}/complete")
async def complete(
    campaign_id: UUID, membership_id: UUID, request: Request, session: Session, user: CurrentUser
) -> CampaignLeadOut:
    return await work.complete(session, campaign_id, membership_id, user, request)
