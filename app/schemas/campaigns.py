from typing import Annotated, Literal
from uuid import UUID

from pydantic import BeforeValidator, Field, StrictInt

from app.core.dates import JalaliDate, JalaliDateTime
from app.core.text import normalize_text
from app.schemas.common import Input, MetadataOut, Output
from app.schemas.marketing import LeadFilters

Title = Annotated[str, BeforeValidator(normalize_text), Field(min_length=1, max_length=200)]
Reason = Annotated[str, BeforeValidator(normalize_text), Field(min_length=1, max_length=255)]


class CampaignCreate(Input):
    title: Title
    start_date: JalaliDate
    end_date: JalaliDate
    include_customers: bool = False


class CampaignUpdate(Input):
    title: Title | None = None
    start_date: JalaliDate | None = None
    end_date: JalaliDate | None = None
    include_customers: bool | None = None


class CampaignOut(MetadataOut):
    title: str
    start_date: JalaliDate
    end_date: JalaliDate
    include_customers: bool
    status: str
    activated_at: JalaliDateTime | None
    closed_at: JalaliDateTime | None


class SelectionChange(Input):
    filters: LeadFilters | None = None
    lead_ids: list[UUID] = Field(default_factory=list, max_length=1000)
    remove_ids: list[UUID] = Field(default_factory=list, max_length=1000)


class CampaignLeadOut(MetadataOut):
    campaign_id: UUID
    lead_id: UUID
    branch_id: UUID
    assigned_to_branch_at: JalaliDateTime
    status: str
    locked_by: UUID | None
    locked_at: JalaliDateTime | None
    completed_at: JalaliDateTime | None


class Reassignment(Input):
    employee_id: UUID


class QuotaOverrideUpdate(Input):
    quota: Annotated[StrictInt, Field(ge=0, le=2147483647)]
    reason: Reason


class VisitCreate(Input):
    visit_date: JalaliDate
    result: Literal["pending", "interested", "not_interested", "no_response"] = "pending"
    description: str | None = Field(None, max_length=4000)
    additional_info: str | None = Field(None, max_length=4000)


class VisitFieldsOut(Output):
    id: UUID
    employee_id: UUID
    visit_date: JalaliDate
    result: str
    description: str | None
    additional_info: str | None
    created_at: JalaliDateTime


class VisitOut(VisitFieldsOut):
    campaign_lead_id: UUID
    visit_count: int
    last_visited_at: JalaliDateTime


class VisitAttemptOut(VisitFieldsOut):
    attempt_no: int
