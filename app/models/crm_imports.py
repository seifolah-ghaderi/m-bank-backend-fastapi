from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BaseMixin


class CrmImport(BaseMixin, Base):
    __tablename__ = "crm_imports"

    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(24))
    file_name: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64))
    total_rows: Mapped[int]
    counts: Mapped[dict] = mapped_column(JSONB, default=dict)
    warnings: Mapped[list] = mapped_column(JSONB, default=list)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(50))
    retry_count: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("kind IN ('organization', 'leads')", name="kind"),
        CheckConstraint(
            "status IN ('queued', 'processing', 'completed', 'completed_with_errors', 'failed')",
            name="status",
        ),
        Index("ix_crm_imports_queue", "kind", "status", "created_at", "id"),
    )


class CrmImportRow(Base):
    __tablename__ = "crm_import_rows"

    import_id: Mapped[UUID] = mapped_column(ForeignKey("crm_imports.id"), primary_key=True)
    row_number: Mapped[int] = mapped_column(primary_key=True)
    outcome: Mapped[str] = mapped_column(String(12))
    error_code: Mapped[str | None] = mapped_column(String(50))
    column: Mapped[str | None] = mapped_column(String(50))
    warnings: Mapped[list] = mapped_column(JSONB, default=list)

    __table_args__ = (
        CheckConstraint("outcome IN ('created', 'unchanged', 'failed')", name="outcome"),
    )
