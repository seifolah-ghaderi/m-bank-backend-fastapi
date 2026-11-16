from uuid import UUID

from pydantic import Field

from app.schemas.common import Input, Mobile


class Login(Input):
    mobile: Mobile
    password: str = Field(min_length=1, max_length=128)


class VerifySms(Input):
    challenge_id: UUID
    code: str = Field(min_length=1, max_length=6)


class ResendSms(Input):
    challenge_id: UUID


class ChangePassword(Input):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
