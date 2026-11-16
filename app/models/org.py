from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BaseMixin, SoftDeleteMixin


class City(BaseMixin, SoftDeleteMixin, Base):
    __tablename__ = "cities"
    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    __table_args__ = (
        Index(
            "uq_cities_name",
            func.lower(name),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class Branch(BaseMixin, SoftDeleteMixin, Base):
    __tablename__ = "branches"
    city_id: Mapped[UUID] = mapped_column(ForeignKey("cities.id"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(150))
    address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    __table_args__ = (
        Index("uq_branches_code", code, unique=True, postgresql_where=text("deleted_at IS NULL")),
        Index(
            "uq_branches_city_name",
            city_id,
            func.lower(name),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )
