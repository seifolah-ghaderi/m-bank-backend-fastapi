from typing import Annotated
from uuid import UUID

from pydantic import BeforeValidator, Field, StrictInt

from app.core.dates import JalaliDateTime
from app.core.text import normalize_text
from app.schemas.common import Input, MetadataOut, Mobile, Name, NationalCode


def product_code(value):
    return normalize_text(value).upper()


ProductCode = Annotated[str, BeforeValidator(product_code), Field(min_length=1, max_length=50)]
Points = Annotated[StrictInt, Field(ge=0, le=2147483647)]


class OccupationCreate(Input):
    name: Name
    is_active: bool = True


class OccupationUpdate(Input):
    name: Name | None = None
    is_active: bool | None = None


class OccupationOut(MetadataOut):
    name: str
    is_active: bool


class BankingProductCreate(OccupationCreate):
    code: ProductCode
    score_value: Points


class BankingProductUpdate(OccupationUpdate):
    code: ProductCode | None = None
    score_value: Points | None = None


class BankingProductOut(OccupationOut):
    code: str
    score_value: int


class LeadFields(Input):
    city_id: UUID
    occupation_id: UUID | None = None
    first_name: Name
    last_name: Name
    mobile: Mobile
    national_code: NationalCode | None = None
    address: str | None = Field(None, max_length=1000)
    referrer: str | None = Field(None, max_length=200)
    additional_info: str | None = Field(None, max_length=4000)


class LeadCreate(LeadFields):
    branch_id: UUID


class LeadBranchAssignment(Input):
    branch_id: UUID


class LeadFilters(Input):
    branch_id: UUID | None = None
    city_id: UUID | None = None
    occupation_id: UUID | None = None
    q: str | None = Field(None, max_length=200)


class LeadOut(MetadataOut):
    branch_id: UUID | None
    city_id: UUID
    occupation_id: UUID | None
    first_name: str
    last_name: str
    mobile: str
    national_code: str | None
    address: str | None
    referrer: str | None
    additional_info: str | None
    is_customer: bool
    archived_at: JalaliDateTime | None
    archived_by: UUID | None
