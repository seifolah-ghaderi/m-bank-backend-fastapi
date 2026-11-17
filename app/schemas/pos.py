import re
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BeforeValidator, Field, model_validator

from app.core.dates import JalaliDate, JalaliDateTime
from app.core.text import normalize_text
from app.schemas.common import Input, MetadataOut, Mobile, NationalCode, Output

Status = Literal["active", "inactive", "under_maintenance", "retired"]
Result = Literal["visited", "owner_unavailable", "shop_closed", "device_not_found"]
Money = Annotated[Decimal, Field(ge=0, max_digits=20, decimal_places=2, allow_inf_nan=False)]
Count = Annotated[int, Field(ge=0, le=9223372036854775807, strict=True)]


def required_text(value):
    if not isinstance(value, str):
        raise ValueError("Text is required")
    return normalize_text(value)


OwnerName = Annotated[str, BeforeValidator(required_text), Field(min_length=2, max_length=200)]
Address = Annotated[str, BeforeValidator(required_text), Field(min_length=5, max_length=1000)]


def device_number(value):
    value = required_text(value).upper()
    if not re.fullmatch(r"[A-Z0-9_-]{3,50}", value):
        raise ValueError("invalid_device_number")
    return value


DeviceNumber = Annotated[str, BeforeValidator(device_number)]


class OwnerCreate(Input):
    owner_name: OwnerName
    owner_mobile: Mobile | None = None
    owner_national_code: NationalCode | None = None
    shop_name: str | None = Field(default=None, max_length=200)
    account_number: str | None = Field(default=None, max_length=100)
    contact_phone: str | None = Field(default=None, max_length=30)


class PosDeviceCreate(OwnerCreate):
    device_number: DeviceNumber
    address: Address
    branch_id: UUID
    status: Status = "active"
    effective_date: JalaliDate | None = None


class PosDeviceUpdate(Input):
    device_number: DeviceNumber | None = None
    owner_name: OwnerName | None = None
    owner_mobile: Mobile | None = None
    owner_national_code: NationalCode | None = None
    shop_name: str | None = Field(default=None, max_length=200)
    account_number: str | None = Field(default=None, max_length=100)
    contact_phone: str | None = Field(default=None, max_length=30)
    address: Address | None = None
    status: Status | None = None


class PosDeviceOut(MetadataOut):
    device_number: str
    owner_name: str
    owner_mobile: str | None
    owner_national_code: str | None
    shop_name: str | None
    account_number: str | None
    contact_phone: str | None
    address: str
    branch_id: UUID
    status: str
    source: str
    last_import_id: UUID | None
    deleted_at: JalaliDateTime | None
    deleted_by: UUID | None


class PosDeviceDetail(PosDeviceOut):
    branch: dict
    open_visit: dict | None
    latest_completed_visit: dict | None
    last_transaction_period_end: JalaliDate | None


class PosTransfer(Input):
    to_branch_id: UUID
    effective_date: JalaliDate | None = None
    reason: str | None = Field(default=None, max_length=255)


class PosOwnerChange(OwnerCreate):
    effective_date: JalaliDate | None = None


class PosBranchHistoryOut(MetadataOut):
    pos_device_id: UUID
    branch_id: UUID
    from_date: JalaliDate
    to_date: JalaliDate | None
    reason: str | None


class PosOwnerHistoryOut(MetadataOut):
    pos_device_id: UUID
    owner_name: str
    owner_mobile: str | None
    owner_national_code: str | None
    shop_name: str | None
    account_number: str | None
    contact_phone: str | None
    from_date: JalaliDate
    to_date: JalaliDate | None


class PosTransactionCreate(Input):
    from_date: JalaliDate
    to_date: JalaliDate
    transaction_amount: Money
    transaction_count: Count

    @model_validator(mode="after")
    def valid_period(self):
        if self.to_date < self.from_date or (self.to_date - self.from_date).days > 365:
            raise ValueError("invalid_period")
        return self


class PosTransactionUpdate(Input):
    from_date: JalaliDate | None = None
    to_date: JalaliDate | None = None
    transaction_amount: Money | None = None
    transaction_count: Count | None = None


class PosTransactionOut(MetadataOut):
    pos_device_id: UUID
    from_date: JalaliDate
    to_date: JalaliDate
    transaction_amount: Decimal
    transaction_count: int
    source: str
    import_id: UUID | None


class PerformanceSettingsUpdate(Input):
    lower_threshold: Money
    upper_threshold: Money

    @model_validator(mode="after")
    def ordered(self):
        if self.upper_threshold <= self.lower_threshold:
            raise ValueError("Thresholds must be ordered")
        return self


class PerformanceSettingsOut(Output):
    lower_threshold: Decimal
    upper_threshold: Decimal
    policy_version: int
    updated_at: JalaliDateTime
    updated_by: UUID | None


class PeriodInput(Input):
    jalali_year: int | None = None
    jalali_month: int | None = None
    from_date: JalaliDate | None = None
    to_date: JalaliDate | None = None


class PosDispatch(PeriodInput):
    pos_device_ids: list[UUID] = Field(min_length=1, max_length=200)
    instructions: str | None = Field(default=None, max_length=2000)


class PosAssign(Input):
    assigned_to: UUID
    due_date: JalaliDate | None = None
    instructions: str | None = Field(default=None, max_length=2000)


class PosBulkAssign(PosAssign):
    visit_ids: list[UUID] = Field(min_length=1, max_length=200)


class PosCancel(Input):
    cancel_reason: str = Field(min_length=1, max_length=255)


class PosComplete(Input):
    result: Result
    tag_codes: list[str] = Field(default_factory=list, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    visited_at: JalaliDateTime | None = None


class PosCorrection(Input):
    result: Result
    tag_codes: list[str] = Field(default_factory=list, max_length=100)
    description: str | None = Field(default=None, max_length=2000)


class SelectionSnapshotOut(Output):
    from_date: JalaliDate
    to_date: JalaliDate
    amount: Decimal | None
    count: Decimal | None
    no_data: bool
    performance: str | None
    lower_threshold: Decimal
    upper_threshold: Decimal
    policy_version: int
    unit: str
    method: str


class PosVisitOut(MetadataOut):
    pos_device_id: UUID
    branch_id: UUID
    selected_by: UUID
    selected_at: JalaliDateTime
    assigned_to: UUID | None
    assigned_by: UUID | None
    assigned_at: JalaliDateTime | None
    due_date: JalaliDate | None
    instructions: str | None
    status: str
    result: str | None
    description: str | None
    visited_at: JalaliDateTime | None
    completed_at: JalaliDateTime | None
    cancelled_at: JalaliDateTime | None
    cancelled_by: UUID | None
    cancel_reason: str | None
    selection_snapshot: SelectionSnapshotOut
    tag_codes: list[str]


class PosTagCreate(Input):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,49}$")
    name: str = Field(min_length=2, max_length=100)
    is_active: bool = True


class PosTagUpdate(Input):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    is_active: bool | None = None


class PosTagOut(MetadataOut):
    code: str
    name: str
    is_active: bool


class ImportRowErrorOut(Output):
    id: int
    row_number: int
    column_name: str | None
    error_code: str
    message: str
    raw_data: dict


class ImportLogOut(MetadataOut):
    import_type: str
    mode: str
    file_name: str
    file_sha256: str
    status: str
    period_from: JalaliDate | None
    period_to: JalaliDate | None
    total_rows: int
    created: int
    updated: int
    unchanged: int
    skipped: int
    failed: int
    success_count: int
    component_counts: dict
    warnings: list
    started_at: JalaliDateTime
    finished_at: JalaliDateTime | None
    errors_preview: list[ImportRowErrorOut] = Field(default_factory=list)
    duplicate_of: UUID | None = None
    errors_url: str
    file_url: str
