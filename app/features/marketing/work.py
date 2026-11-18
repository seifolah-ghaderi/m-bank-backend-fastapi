from sqlalchemy import and_, func, select
from sqlalchemy.orm import aliased

from app.core import dates
from app.core.audit import record
from app.core.errors import DomainError
from app.core.pagination import paginate
from app.core.validation import input_values
from app.features.marketing.campaigns import STAFF, assigned_scope, get_campaign
from app.models import (
    BankingProduct,
    Branch,
    Campaign,
    CampaignLead,
    CampaignQuotaOverride,
    CampaignVisit,
    Customer,
    CustomerProduct,
    Lead,
    User,
    VisitAttempt,
)


async def list_work(session, campaign_id, user, page):
    await get_campaign(session, campaign_id, user)
    statement = assigned_scope(
        select(CampaignLead)
        .join(Campaign, Campaign.id == CampaignLead.campaign_id)
        .where(CampaignLead.campaign_id == campaign_id, CampaignLead.selected),
        user,
    )
    result = await paginate(
        session,
        statement,
        page,
        {"assigned_at": CampaignLead.assigned_to_branch_at, "status": CampaignLead.status},
        "assigned_at",
        CampaignLead.id,
    )
    ids = [item.lead_id for item in result["items"]]
    leads = {lead.id: lead for lead in await session.scalars(select(Lead).where(Lead.id.in_(ids)))}
    held = {}
    for lead_id, name in await session.execute(
        select(Customer.lead_id, BankingProduct.name)
        .join(CustomerProduct, CustomerProduct.customer_id == Customer.id)
        .join(BankingProduct, BankingProduct.id == CustomerProduct.banking_product_id)
        .where(Customer.lead_id.in_(ids))
        .order_by(BankingProduct.name, BankingProduct.id)
    ):
        held.setdefault(lead_id, []).append(name)
    return result, leads, held


async def active_campaign(session, campaign_id):
    campaign = await session.scalar(
        select(Campaign)
        .where(Campaign.id == campaign_id, Campaign.deleted_at.is_(None))
        .with_for_update(read=True)
    )
    if campaign is None or campaign.status == "draft":
        raise DomainError(404, "not_found")
    if campaign.status != "active":
        raise DomainError(409, "campaign_closed")
    return campaign


async def get_member(session, campaign_id, membership_id, user, *, mutate=False, pick=False):
    scope = [
        CampaignLead.id == membership_id,
        CampaignLead.campaign_id == campaign_id,
        CampaignLead.selected,
    ]
    if user.role != "supervisor":
        scope.append(CampaignLead.branch_id == user.branch_id)
    if user.role == "employee" and not pick:
        scope.append(CampaignLead.locked_by == user.id)
    statement = select(CampaignLead).where(*scope)
    if mutate:
        # Establish the caller's scope before acquiring locks or reporting a campaign status.
        lead_id = await session.scalar(statement.with_only_columns(CampaignLead.lead_id))
        if lead_id is None:
            raise DomainError(404, "not_found")
        await active_campaign(session, campaign_id)
        await session.execute(select(Lead.id).where(Lead.id == lead_id).with_for_update())
        statement = statement.with_for_update()
    member = await session.scalar(statement)
    if member is None:
        raise DomainError(404, "not_found")
    return member


async def quota_locks(session, campaign_id, employee_ids):
    for employee_id in sorted(set(employee_ids)):
        key = f"campaign-quota:{campaign_id}:{employee_id}"
        await session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0))))


async def employees(session, campaign_id, branch_id, *, employee_id=None):
    branch = await session.get(Branch, branch_id)
    if branch is None or branch.deleted_at is not None:
        raise DomainError(404, "not_found")
    if not branch.is_active:
        return []
    count_leads = await session.scalar(
        select(func.count())
        .select_from(CampaignLead)
        .where(
            CampaignLead.campaign_id == campaign_id,
            CampaignLead.branch_id == branch_id,
            CampaignLead.selected,
        )
    )
    users = (
        await session.scalars(
            select(User)
            .where(User.branch_id == branch_id, *STAFF)
            .order_by(User.last_name, User.first_name, User.id)
        )
    ).all()
    if not users:
        return []
    computed = (count_leads + len(users) - 1) // len(users)
    user_ids = [employee_id] if employee_id else [user.id for user in users]
    assignment = aliased(CampaignLead)
    counts = {
        key: (picked, finished)
        for key, picked, finished in await session.execute(
            select(
                assignment.locked_by,
                func.count(),
                func.count().filter(assignment.status == "completed"),
            )
            .where(
                assignment.campaign_id == campaign_id,
                assignment.branch_id == branch_id,
                assignment.selected,
                assignment.locked_by.in_(user_ids),
            )
            .group_by(assignment.locked_by)
        )
    }
    overrides = dict(
        (
            await session.execute(
                select(CampaignQuotaOverride.employee_id, CampaignQuotaOverride.quota).where(
                    CampaignQuotaOverride.campaign_id == campaign_id,
                    CampaignQuotaOverride.employee_id.in_(user_ids),
                )
            )
        ).all()
    )
    items = []
    for user in users:
        if user.id not in user_ids:
            continue
        picked, finished = counts.get(user.id, (0, 0))
        effective = overrides.get(user.id, computed)
        items.append(
            {
                "employee_id": user.id,
                "computed_quota": computed,
                "effective_quota": effective,
                "picked_count": picked,
                "finished_count": finished,
                "remaining": max(0, effective - picked),
                "has_override": user.id in overrides,
            }
        )
    return items


async def branch_capacity(session, campaign_id, branch_id, user):
    if user.role != "supervisor" and user.branch_id != branch_id:
        raise DomainError(404, "not_found")
    campaign = await session.get(Campaign, campaign_id)
    membership = await session.scalar(
        select(CampaignLead.id)
        .where(
            CampaignLead.campaign_id == campaign_id,
            CampaignLead.branch_id == branch_id,
            CampaignLead.selected,
        )
        .limit(1)
    )
    if (
        not campaign
        or campaign.deleted_at
        or (user.role != "supervisor" and (campaign.status == "draft" or not membership))
    ):
        raise DomainError(404, "not_found")
    return await employees(
        session, campaign_id, branch_id, employee_id=user.id if user.role == "employee" else None
    )


async def override(session, campaign_id, branch_id, employee_id, user, request, body):
    if user.role != "branch_manager":
        raise DomainError(403, "forbidden")
    if user.branch_id != branch_id:
        raise DomainError(404, "not_found")
    await get_campaign(session, campaign_id, user)
    await active_campaign(session, campaign_id)
    await quota_locks(session, campaign_id, [employee_id])
    if not await employees(session, campaign_id, branch_id, employee_id=employee_id):
        raise DomainError(404, "not_found")
    row = await session.scalar(
        select(CampaignQuotaOverride).where(
            and_(
                CampaignQuotaOverride.campaign_id == campaign_id,
                CampaignQuotaOverride.employee_id == employee_id,
            )
        )
    )
    if row is None:
        row = CampaignQuotaOverride(
            campaign_id=campaign_id, employee_id=employee_id, created_by=user.id
        )
        session.add(row)
    row.quota = body.quota
    row.reason = body.reason
    row.updated_by = user.id
    await session.flush()
    record(
        session,
        user,
        "quota_override",
        "campaign_quota_overrides",
        row.id,
        after={"quota": row.quota, "reason": row.reason},
        request=request,
    )
    return {"employee_id": employee_id, "quota": row.quota, "reason": row.reason}


async def assign(session, campaign_id, membership_id, user, request, *, employee_id=None):
    picking = employee_id is None
    if user.role != ("employee" if picking else "branch_manager"):
        raise DomainError(403, "forbidden")
    member = await get_member(session, campaign_id, membership_id, user, mutate=True, pick=picking)
    status = "available" if picking else "locked"
    if member.status != status:
        raise DomainError(409, "lead_unavailable")
    target = user.id if picking else employee_id
    affected = [target] if picking else [target, member.locked_by]
    await quota_locks(session, campaign_id, affected)
    capacity = await employees(session, campaign_id, member.branch_id, employee_id=target)
    if not capacity:
        raise DomainError(409, "employee_unavailable")
    if picking and not capacity[0]["remaining"]:
        raise DomainError(409, "quota_reached")
    previous = member.locked_by
    member.locked_by = target
    member.updated_by = user.id
    if picking:
        member.status = "locked"
        member.locked_at = dates.now()
    record(
        session,
        user,
        "pick" if picking else "reassign",
        "campaign_leads",
        member.id,
        {"locked_by": previous},
        {"locked_by": target},
        request,
    )
    await session.flush()
    return member


async def get_visit(session, membership_id):
    return await session.scalar(
        select(CampaignVisit).where(CampaignVisit.campaign_lead_id == membership_id)
    )


async def append_visit(session, campaign_id, membership_id, user, request, body):
    if user.role != "employee":
        raise DomainError(403, "forbidden")
    member = await get_member(session, campaign_id, membership_id, user, mutate=True)
    if member.status != "locked":
        raise DomainError(409, "lead_unavailable")
    if body.visit_date > dates.today():
        raise DomainError(422, "future_visit_date")
    now = dates.now()
    values = input_values(body) | {"employee_id": user.id}
    visit = await get_visit(session, member.id)
    if visit is None:
        visit = CampaignVisit(
            campaign_lead_id=member.id, visit_count=0, created_at=now, created_by=user.id
        )
        session.add(visit)
    visit.visit_count += 1
    visit.last_visited_at = now
    visit.updated_by = user.id
    for key, value in values.items():
        setattr(visit, key, value)
    await session.flush()
    attempt = VisitAttempt(
        visit_id=visit.id,
        attempt_no=visit.visit_count,
        created_at=now,
        created_by=user.id,
        updated_by=user.id,
        **values,
    )
    session.add(attempt)
    await session.flush()
    record(
        session,
        user,
        "visit_recorded",
        "visits",
        visit.id,
        after={"attempt_id": attempt.id, "result": attempt.result},
        request=request,
    )
    return visit


async def visit_history(session, campaign_id, membership_id, user, page):
    await get_campaign(session, campaign_id, user)
    member = await get_member(session, campaign_id, membership_id, user)
    visit = await get_visit(session, member.id)
    if visit is None:
        raise DomainError(404, "not_found")
    return visit, await paginate(
        session,
        select(VisitAttempt).where(VisitAttempt.visit_id == visit.id),
        page,
        {"attempt_no": VisitAttempt.attempt_no},
        "attempt_no",
        VisitAttempt.id,
    )


async def complete(session, campaign_id, membership_id, user, request):
    if user.role != "employee":
        raise DomainError(403, "forbidden")
    member = await get_member(session, campaign_id, membership_id, user, mutate=True)
    if member.status != "locked":
        raise DomainError(409, "lead_unavailable")
    if await get_visit(session, member.id) is None:
        raise DomainError(409, "visit_required")
    member.status = "completed"
    member.completed_at = dates.now()
    member.updated_by = user.id
    record(session, user, "complete", "campaign_leads", member.id, request=request)
    await session.flush()
    return member
