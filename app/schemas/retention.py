from typing import Annotated

from pydantic import Field, StrictInt

from app.schemas.common import Input, MetadataOut, Name

DayOffset = Annotated[StrictInt, Field(gt=0, le=2147483647)]


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
