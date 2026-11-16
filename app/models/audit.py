from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core import dates
from app.models.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dates.now(), server_default=func.now()
    )
    actor_id: Mapped[UUID | None] = mapped_column()
    actor_role: Mapped[str | None] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(40))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[UUID | None] = mapped_column()
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(String(45))
    request_id: Mapped[UUID | None]
    __table_args__ = (
        Index("ix_audit_logs_entity", entity_type, entity_id, occurred_at.desc()),
        Index("ix_audit_logs_actor", actor_id, occurred_at.desc()),
    )
