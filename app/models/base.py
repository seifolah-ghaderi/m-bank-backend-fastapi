from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from uuid_utils import uuid7

from app.core import dates


def new_id() -> UUID:
    return UUID(str(uuid7()))


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class BaseMixin:
    __mapper_args__ = {"eager_defaults": True}
    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dates.now(), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: dates.now(),
        server_default=func.now(),
        onupdate=lambda: dates.now(),
    )
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", use_alter=True))
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", use_alter=True))


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", use_alter=True))


def not_deleted(model):
    return model.deleted_at.is_(None)
