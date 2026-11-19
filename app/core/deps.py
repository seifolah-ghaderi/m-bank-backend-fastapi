from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import DomainError
from app.core.security import decode_access
from app.models import User

Session = Annotated[AsyncSession, Depends(get_session, scope="function")]
BearerCredentials = Annotated[
    HTTPAuthorizationCredentials | None,
    Depends(HTTPBearer(auto_error=False, scheme_name="BearerAuth", bearerFormat="JWT")),
]


@dataclass(frozen=True)
class Scope:
    role: str
    branch_id: UUID | None
    user_id: UUID

    def apply(self, statement, model):
        if self.role == "supervisor":
            return statement
        if model is User and self.role == "employee":
            return statement.where(User.id == self.user_id)
        if model.__tablename__ == "pos_visits" and self.role == "employee":
            return statement.where(model.assigned_to == self.user_id)
        field = model.id if model.__tablename__ == "branches" else model.branch_id
        return statement.where(field == self.branch_id)


def scope_for(user):
    return Scope(user.role, user.branch_id, user.id)


def eligible(user):
    if user is None or not user.is_active or user.deleted_at is not None:
        raise DomainError(401, "account_disabled")


async def current_user(request: Request, session: Session, credentials: BearerCredentials):
    if credentials is None:
        raise DomainError(401, "invalid_credentials")
    user_id = decode_access(request.app.state.settings, credentials.credentials)
    user = await session.scalar(select(User).where(User.id == user_id))
    eligible(user)
    allowed = {"/api/v1/auth/me", "/api/v1/auth/change-password", "/api/v1/auth/logout"}
    if user.must_change_password and request.url.path not in allowed:
        raise DomainError(403, "password_change_required")
    return user


CurrentUser = Annotated[User, Depends(current_user, scope="function")]


def require_roles(user, *roles):
    if user.role not in roles:
        raise DomainError(403, "forbidden")


async def supervisor(user: CurrentUser):
    require_roles(user, "supervisor")
    return user


Supervisor = Annotated[User, Depends(supervisor, scope="function")]
