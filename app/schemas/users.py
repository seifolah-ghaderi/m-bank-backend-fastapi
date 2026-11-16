from typing import Literal
from uuid import UUID

from app.core.dates import JalaliDateTime
from app.schemas.common import Input, MetadataOut, Mobile, Name, NationalCode

Role = Literal["supervisor", "branch_manager", "employee"]


class UserCreate(Input):
    first_name: Name
    last_name: Name
    mobile: Mobile
    national_code: NationalCode | None = None
    role: Role
    branch_id: UUID | None = None
    is_active: bool = True


class UserUpdate(Input):
    first_name: Name | None = None
    last_name: Name | None = None
    mobile: Mobile | None = None
    national_code: NationalCode | None = None
    role: Role | None = None
    branch_id: UUID | None = None
    is_active: bool | None = None


class UserOut(MetadataOut):
    first_name: str
    last_name: str
    mobile: str
    national_code: str | None
    role: str
    branch_id: UUID | None
    is_active: bool
    must_change_password: bool
    last_login_at: JalaliDateTime | None
    password_changed_at: JalaliDateTime | None


class UserCreated(UserOut):
    temporary_password: str
