from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StrictInt, StringConstraints

from app.core.dates import JalaliDate, JalaliDateTime
from app.schemas.common import Input, MetadataOut, Name, Output

DayOffset = Annotated[StrictInt, Field(gt=0, le=2147483647)]
RetentionTaskStatus = Literal["open", "completed", "cancelled"]


class RetentionScheduleCreate(Input):
    label: Name
    days_after_conversion: DayOffset
    requires_approval: bool = False
    is_active: bool = True


class RetentionScheduleUpdate(Input):
    label: Name | None = None
    days_after_conversion: DayOffset | None = None
    requires_approval: bool | None = None
    is_active: bool | None = None


class RetentionScheduleOut(MetadataOut):
    label: str
    days_after_conversion: int
    requires_approval: bool
    is_active: bool


class RetentionTaskComplete(Input):
    visit_date: JalaliDate
    result: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
    notes: str | None = None


class RetentionTaskListItem(Output):
    id: UUID
    customer_id: UUID
    schedule_id: UUID
    label: str
    assigned_to: UUID
    due_date: JalaliDate
    status: RetentionTaskStatus
    visit_date: JalaliDate | None
    result: str | None
    completed_at: JalaliDateTime | None
    completed_by: UUID | None


class RetentionTaskContactOut(Output):
    first_name: str
    last_name: str
    phone: str
    address: str
    city_id: UUID


class RetentionTaskOut(RetentionTaskListItem):
    customer: RetentionTaskContactOut
    notes: str | None
