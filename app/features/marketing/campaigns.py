from sqlalchemy import and_, or_, select

from app.core import dates
from app.core.audit import record, snapshot
from app.core.errors import DomainError
from app.core.pagination import paginate
from app.core.validation import input_values, validated_changes
from app.features.marketing.leads import filter_leads
from app.models import Branch, Campaign, CampaignLead, Lead, User

CAMPAIGN_SORT = {
    "title": Campaign.title,
    "created_at": Campaign.created_at,
    "start_date": Campaign.start_date,
}
STAFF = (User.role == "employee", User.is_active, User.deleted_at.is_(None))


def assigned_scope(statement, user):
    if user.role == "supervisor":
        return statement
    statement = statement.where(CampaignLead.branch_id == user.branch_id)
    if user.role == "employee":
        return statement.where(
            or_(
                CampaignLead.locked_by == user.id,
                and_(Campaign.status == "active", CampaignLead.status == "available"),
            )
        )
    return statement


def visible_campaigns(user):
    statement = select(Campaign).where(Campaign.deleted_at.is_(None))
    if user.role != "supervisor":
        membership = (
            select(CampaignLead.id)
            .where(
                CampaignLead.campaign_id == Campaign.id,
                CampaignLead.selected,
                CampaignLead.branch_id == user.branch_id,
            )
            .correlate(Campaign)
        )
        if user.role == "employee":
            membership = membership.where(
                or_(Campaign.status == "active", CampaignLead.locked_by == user.id)
            )
        statement = statement.where(Campaign.status != "draft", membership.exists())
    return statement


async def list_campaigns(session, user, page, status):
    statement = visible_campaigns(user)
    if status:
        statement = statement.where(Campaign.status == status)
    return await paginate(session, statement, page, CAMPAIGN_SORT, "-created_at", Campaign.id)


async def get_campaign(session, campaign_id, user, *, lock=False, shared=False):
    statement = visible_campaigns(user).where(Campaign.id == campaign_id)
    if lock:
        statement = statement.with_for_update(read=shared)
    campaign = await session.scalar(statement)
    if campaign is None:
        raise DomainError(404, "not_found")
    return campaign


def require_draft(campaign):
    if campaign.status != "draft":
        raise DomainError(409, "campaign_not_draft")


async def save_campaign(session, user, request, body, campaign_id=None):
    before = None
    if campaign_id is None:
        campaign = Campaign(**input_values(body), created_by=user.id)
        session.add(campaign)
    else:
        campaign = await get_campaign(session, campaign_id, user, lock=True)
        require_draft(campaign)
        before = snapshot(campaign)
        for key, value in validated_changes(body, type(body).model_fields).items():
            setattr(campaign, key, value)
    if campaign.end_date < campaign.start_date:
        raise DomainError(422, "invalid_campaign_dates")
    campaign.updated_by = user.id
    await session.flush()
    record(
        session,
        user,
        "create" if before is None else "update",
        "campaigns",
        campaign.id,
        before,
        snapshot(campaign),
        request,
    )
    return campaign


async def delete_campaign(session, campaign_id, user, request):
    campaign = await get_campaign(session, campaign_id, user, lock=True)
    require_draft(campaign)
    campaign.deleted_at = dates.now()
    campaign.updated_by = user.id
    record(session, user, "delete", "campaigns", campaign.id, request=request)
    await session.flush()


def eligible_selection(campaign):
    query = (
        select(Lead)
        .join(Branch, Lead.branch_id == Branch.id)
        .where(Lead.archived_at.is_(None), Branch.is_active, Branch.deleted_at.is_(None))
    )
    if not campaign.include_customers:
        query = query.where(~Lead.is_customer)
    return query


async def preview(session, campaign_id, user, page, filters):
    campaign = await get_campaign(session, campaign_id, user)
    require_draft(campaign)
    statement = filter_leads(eligible_selection(campaign), filters)
    return await paginate(
        session,
        statement,
        page,
        {"name": Lead.last_name, "created_at": Lead.created_at},
        "name",
        Lead.id,
    )


async def change_selection(session, campaign_id, user, request, body):
    campaign = await get_campaign(session, campaign_id, user, lock=True)
    require_draft(campaign)
    included = set(body.lead_ids)
    removed = set(body.remove_ids)
    if included & removed:
        raise DomainError(422, "selection_conflict")
    targets = eligible_selection(campaign)
    if body.filters is not None:
        targets = filter_leads(targets, body.filters)
    filter_ids = select(targets.subquery().c.id) if body.filters is not None else None
    if filter_ids is not None:
        targets = eligible_selection(campaign).where(
            or_(Lead.id.in_(filter_ids), Lead.id.in_(included)), Lead.id.not_in(removed)
        )
    else:
        targets = targets.where(Lead.id.in_(included))
    selected_leads = (await session.scalars(targets.order_by(Lead.id))).all()
    target_ids = {lead.id for lead in selected_leads}
    if missing := included - target_ids:
        raise DomainError(
            422, "ineligible_lead_selection", details={"lead_ids": sorted(map(str, missing))}
        )
    rows = await session.scalars(
        select(CampaignLead).where(CampaignLead.campaign_id == campaign.id)
    )
    existing = {item.lead_id: item for item in rows}
    added, deselected = 0, 0
    for lead in selected_leads:
        item = existing.get(lead.id)
        if item is None:
            session.add(
                CampaignLead(
                    campaign_id=campaign.id,
                    lead_id=lead.id,
                    branch_id=lead.branch_id,
                    assigned_to_branch_at=dates.now(),
                    created_by=user.id,
                    updated_by=user.id,
                )
            )
            added += 1
        elif not item.selected:
            item.selected = True
            item.updated_by = user.id
            added += 1
    for lead_id in removed:
        item = existing.get(lead_id)
        if item and item.selected:
            item.selected = False
            item.updated_by = user.id
            deselected += 1
    await session.flush()
    result = {"added": added, "removed": deselected}
    record(
        session, user, "selection_changed", "campaigns", campaign.id, after=result, request=request
    )
    return result


async def transition(session, campaign_id, user, request, *, activate):
    campaign = await get_campaign(session, campaign_id, user, lock=True)
    if campaign.status != ("draft" if activate else "active"):
        raise DomainError(409, "invalid_campaign_transition")
    rows = (
        await session.scalars(
            select(CampaignLead).where(
                CampaignLead.campaign_id == campaign.id, CampaignLead.selected
            )
        )
    ).all()
    empty_branches = []
    if activate:
        ids = {row.lead_id for row in rows}
        await session.execute(
            select(Lead.id).where(Lead.id.in_(ids)).order_by(Lead.id).with_for_update()
        )
        allowed = set(
            await session.scalars(
                eligible_selection(campaign).with_only_columns(Lead.id).where(Lead.id.in_(ids))
            )
        )
        if ids - allowed:
            raise DomainError(
                409,
                "ineligible_lead_selection",
                details={"lead_ids": sorted(map(str, ids - allowed))},
            )
        collisions = list(
            await session.scalars(
                select(CampaignLead.lead_id)
                .where(CampaignLead.lead_id.in_(ids), CampaignLead.reserved)
                .order_by(CampaignLead.lead_id)
            )
        )
        if collisions:
            raise DomainError(
                409, "lead_already_reserved", details={"lead_ids": list(map(str, collisions))}
            )
        branches = {row.branch_id for row in rows}
        staffed = set(
            await session.scalars(
                select(User.branch_id).where(User.branch_id.in_(branches), *STAFF)
            )
        )
        empty_branches = sorted(branches - staffed)
        campaign.status = "active"
        campaign.activated_at = dates.now()
    else:
        campaign.status = "closed"
        campaign.closed_at = dates.now()
    for row in rows:
        row.reserved = activate
        row.updated_by = user.id
    campaign.updated_by = user.id
    record(
        session,
        user,
        "activate" if activate else "close",
        "campaigns",
        campaign.id,
        after={"status": campaign.status},
        request=request,
    )
    await session.flush()
    return campaign, empty_branches
