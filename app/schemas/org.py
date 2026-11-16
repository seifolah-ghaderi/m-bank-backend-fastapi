import re
from typing import Annotated
from uuid import UUID

from pydantic import BeforeValidator, Field

from app.core.text import normalize_text
from app.schemas.common import BranchName, IdentityOut, Input, MetadataOut, Name, Output


def branch_code(value):
    value = normalize_text(value).upper()
    if not re.fullmatch(r"[A-Z0-9-]{2,20}", value):
        raise ValueError("Invalid branch code")
    return value


Code = Annotated[str, BeforeValidator(branch_code)]


class CityCreate(Input):
    name: Name
    is_active: bool = True


class CityUpdate(Input):
    name: Name | None = None
    is_active: bool | None = None


class CityOut(MetadataOut):
    name: str
    is_active: bool


class BranchCreate(Input):
    city_id: UUID
    code: Code
    name: BranchName
    address: str | None = Field(default=None, max_length=1000)
    phone: str | None = Field(default=None, max_length=20)
    is_active: bool = True


class BranchUpdate(Input):
    city_id: UUID | None = None
    code: Code | None = None
    name: BranchName | None = None
    address: str | None = Field(default=None, max_length=1000)
    phone: str | None = Field(default=None, max_length=20)
    is_active: bool | None = None


class ManagerOut(Output):
    id: UUID
    full_name: str
    mobile: str


class BranchOut(MetadataOut):
    city_id: UUID
    code: str
    name: str
    address: str | None
    phone: str | None
    is_active: bool
    city: IdentityOut
    manager: ManagerOut | None
    active_employee_count: int
