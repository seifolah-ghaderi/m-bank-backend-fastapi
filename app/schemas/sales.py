from typing import Annotated
from uuid import UUID

from pydantic import BeforeValidator, Field

from app.core.dates import JalaliDate, JalaliDateTime
from app.core.text import digits
from app.schemas.common import Input, MetadataOut, Name, NationalCode, Output


def identifier(value):
    if not isinstance(value, str):
        raise ValueError("Expected text")
    return digits(value).strip()


AccountReference = Annotated[str, BeforeValidator(identifier), Field(min_length=1, max_length=100)]
CustomerCode = Annotated[str, BeforeValidator(identifier), Field(min_length=1, max_length=50)]
Phone = Annotated[
    str,
    BeforeValidator(identifier),
    Field(min_length=5, max_length=20, pattern=r"^[+0-9][0-9 ()-]*$"),
]
Address = Annotated[str, Field(min_length=1, max_length=1000, pattern=r"\S")]


class CustomerProfile(Input):
    first_name: Name | None = None
    last_name: Name | None = None
    phone: Phone | None = None
    address: Address | None = None
    city_id: UUID | None = None
    national_code: NationalCode | None = None
    customer_code: CustomerCode | None = None


class CustomerUpdate(Input):
    first_name: Name | None = None
    last_name: Name | None = None
    phone: Phone | None = None
    address: Address | None = None
    city_id: UUID | None = None


class CustomerFilters(Input):
    branch_id: UUID | None = None
    city_id: UUID | None = None
    product_id: UUID | None = None
    customer_since_from: JalaliDate | None = None
    customer_since_to: JalaliDate | None = None
    q: str | None = Field(None, max_length=200)


class CustomerOut(MetadataOut):
    lead_id: UUID
    branch_id: UUID
    city_id: UUID
    acquired_by: UUID
    first_sale_id: UUID
    customer_code: str
    first_name: str
    last_name: str
    phone: str
    address: str
    national_code: str | None
    customer_since: JalaliDate
    converted_at: JalaliDateTime


class SaleCreate(Input):
    visit_id: UUID
    banking_product_id: UUID
    account_number: AccountReference
    proof_text: str | None = Field(None, max_length=4000)
    description: str | None = Field(None, max_length=4000)
    customer_profile: CustomerProfile | None = None


class SaleUpdate(Input):
    banking_product_id: UUID | None = None
    account_number: AccountReference | None = None
    proof_text: str | None = Field(None, max_length=4000)
    description: str | None = Field(None, max_length=4000)
    customer_profile: CustomerProfile | None = None


class SaleOut(MetadataOut):
    lead_id: UUID
    customer_id: UUID | None
    visit_id: UUID
    employee_id: UUID
    banking_product_id: UUID
    account_number: str
    proof_text: str | None
    description: str | None
    status: str
    registered_at: JalaliDateTime
    submitted_at: JalaliDateTime | None
    last_submitted_at: JalaliDateTime | None
    verified_at: JalaliDateTime | None
    verified_by: UUID | None
    rejection_reason: str | None
    resubmit_count: int


class SubmitSales(Input):
    sale_ids: list[UUID] = Field(min_length=1, max_length=100)


class ReviewSelection(Input):
    submission_id: UUID


class RejectSale(ReviewSelection):
    reason: str = Field(min_length=1, max_length=500, pattern=r"\S")


class BatchReviewItem(ReviewSelection):
    sale_id: UUID


class BatchApproval(Input):
    sales: list[BatchReviewItem] = Field(min_length=1, max_length=100)


class SaleSubmissionOut(Output):
    id: UUID
    revision: int
    profile: CustomerProfile | None
    banking_product_id: UUID
    account_number: str
    proof_text: str
    description: str | None
    created_at: JalaliDateTime
