from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    literal_column,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BaseMixin, SoftDeleteMixin, new_id


class User(BaseMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"
    branch_id: Mapped[UUID | None] = mapped_column(ForeignKey("branches.id"), index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    mobile: Mapped[str] = mapped_column(String(11))
    national_code: Mapped[str | None] = mapped_column(String(10))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    must_change_password: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    failed_login_count: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("role IN ('supervisor','branch_manager','employee')", name="role"),
        CheckConstraint(
            "(role = 'supervisor' AND branch_id IS NULL) OR "
            "(role <> 'supervisor' AND branch_id IS NOT NULL)",
            name="branch_by_role",
        ),
        Index("uq_users_mobile", mobile, unique=True, postgresql_where=text("deleted_at IS NULL")),
        Index(
            "uq_users_national_code",
            national_code,
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND national_code IS NOT NULL"),
        ),
        Index(
            "uq_users_one_manager_per_branch",
            branch_id,
            unique=True,
            postgresql_where=text("role = 'branch_manager' AND deleted_at IS NULL"),
        ),
        Index(
            "ix_users_name_search",
            literal_column("((first_name::text || ' '::text) || last_name::text)").label(
                "full_name"
            ),
            postgresql_using="gin",
            postgresql_ops={"full_name": "gin_trgm_ops"},
        ),
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    ip: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class LoginChallenge(Base):
    __tablename__ = "login_challenges"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    mobile: Mapped[str] = mapped_column(String(11))
    code_digest: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    failed_attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_state: Mapped[str] = mapped_column(String(10), default="pending")
    __table_args__ = (
        CheckConstraint("delivery_state IN ('pending','sent','failed')", name="delivery_state"),
        CheckConstraint("failed_attempts >= 0", name="attempts"),
        Index(
            "uq_login_challenges_pending_user",
            user_id,
            unique=True,
            postgresql_where=text("consumed_at IS NULL AND invalidated_at IS NULL"),
        ),
    )
