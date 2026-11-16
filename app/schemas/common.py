from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from app.core.dates import JalaliDateTime
from app.core.text import mobile, national_code, normalize_text

Mobile = Annotated[str, BeforeValidator(mobile)]
NationalCode = Annotated[str, BeforeValidator(national_code)]
Name = Annotated[str, BeforeValidator(normalize_text), Field(min_length=2, max_length=100)]
BranchName = Annotated[str, BeforeValidator(normalize_text), Field(min_length=2, max_length=150)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MetadataOut(Output):
    id: UUID
    created_at: JalaliDateTime
    updated_at: JalaliDateTime
    created_by: UUID | None
    updated_by: UUID | None


class IdentityOut(Output):
    id: UUID
    name: str
