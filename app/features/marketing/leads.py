from sqlalchemy import func, select

from app.core import dates
from app.core.audit import record
from app.core.errors import DomainError
from app.core.pagination import paginate
from app.core.text import normalize_text
from app.core.validation import input_values
from app.models import Branch, CampaignLead, City, Lead, Occupation, ProductSale


def filter_leads(statement, filters):
    for column in (Lead.branch_id, Lead.city_id, Lead.occupation_id):
        if (value := getattr(filters, column.key)) is not None:
            statement = statement.where(column == value)
    if filters.q and (query := normalize_text(filters.q).lower()):
        name = func.lower(Lead.first_name + " " + Lead.last_name)
        statement = statement.where(name.contains(query, autoescape=True))
    return statement


async def list_leads(session, page, filters, include_archived, archived):
    statement = filter_leads(select(Lead), filters)
    if archived is True:
        statement = statement.where(Lead.archived_at.is_not(None))
    elif archived is False or not include_archived:
        statement = statement.where(Lead.archived_at.is_(None))
    return await paginate(
        session,
        statement,
        page,
        {"name": Lead.last_name, "created_at": Lead.created_at},
        "-created_at",
        Lead.id,
    )


async def get_lead(session, lead_id):
    lead = await session.get(Lead, lead_id)
    if lead is None:
        raise DomainError(404, "not_found")
    return lead


async def archive_lead(session, lead_id, user, request, *, archive):
    lead = await session.scalar(select(Lead).where(Lead.id == lead_id).with_for_update())
    if lead is None:
        raise DomainError(404, "not_found")
    if (lead.archived_at is not None) == archive:
        return lead
    if archive:
        if lead.is_customer:
            raise DomainError(409, "lead_is_customer")
        reserved = select(CampaignLead.id).where(
            CampaignLead.lead_id == lead.id, CampaignLead.reserved
        )
        nonfinal = select(ProductSale.id).where(
            ProductSale.lead_id == lead.id,
            ProductSale.status.in_(("draft", "submitted", "rejected")),
        )
        if await session.scalar(select(reserved.exists() | nonfinal.exists())):
            raise DomainError(409, "lead_has_open_work")
    previous = lead.archived_at
    lead.archived_at = dates.now() if archive else None
    lead.archived_by = user.id if archive else None
    lead.updated_by = user.id
    record(
        session,
        user,
        "archive" if archive else "restore",
        "leads",
        lead.id,
        {"archived_at": previous},
        {"archived_at": lead.archived_at},
        request,
    )
    await session.flush()
    return lead


async def create_lead(session, body, user, request):
    for model, key, code in (
        (Branch, body.branch_id, "invalid_branch"),
        (City, body.city_id, "invalid_city"),
        (Occupation, body.occupation_id, "invalid_occupation"),
    ):
        if key is not None:
            record_row = await session.get(model, key)
            if (
                not record_row
                or not record_row.is_active
                or getattr(record_row, "deleted_at", None)
            ):
                raise DomainError(422, code)
    lead = Lead(**input_values(body), created_by=user.id, updated_by=user.id)
    session.add(lead)
    await session.flush()
    record(
        session,
        user,
        "create",
        "leads",
        lead.id,
        after={"branch_id": lead.branch_id},
        request=request,
    )
    return lead
