from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BaseMixin, SoftDeleteMixin

OPEN_STATES = ("pending_assignment", "assigned")
OWNER_FIELDS = (
    "owner_name",
    "owner_mobile",
    "owner_national_code",
    "shop_name",
    "account_number",
    "contact_phone",
)


class OwnerFields:
    owner_name: Mapped[str] = mapped_column(String(200))
    owner_mobile: Mapped[str | None] = mapped_column(String(11))
    owner_national_code: Mapped[str | None] = mapped_column(String(10))
    shop_name: Mapped[str | None] = mapped_column(String(200))
    account_number: Mapped[str | None] = mapped_column(String(100))
    contact_phone: Mapped[str | None] = mapped_column(String(30))


class PosDevice(OwnerFields, BaseMixin, SoftDeleteMixin, Base):
    __tablename__ = "pos_devices"
    device_number: Mapped[str] = mapped_column(String(50))
    address: Mapped[str] = mapped_column(Text)
    branch_id: Mapped[UUID] = mapped_column(ForeignKey("branches.id"))
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    source: Mapped[str] = mapped_column(String(10), default="manual")
    last_import_id: Mapped[UUID | None] = mapped_column(ForeignKey("import_logs.id"))
    __table_args__ = (
        Index(
            "uq_pos_devices_number",
            "device_number",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_pos_devices_branch_status", "branch_id", "status"),
        Index(
            "ix_pos_devices_search",
            text(
                "(owner_name || ' ' || coalesce(shop_name, '') || ' ' || "
                "device_number) gin_trgm_ops"
            ),
            postgresql_using="gin",
        ),
        CheckConstraint(
            "status IN ('active','inactive','under_maintenance','retired')", name="status"
        ),
        CheckConstraint("source IN ('manual','import')", name="source"),
    )


def history_constraints(table):
    return (
        CheckConstraint("to_date IS NULL OR to_date >= from_date", name="period"),
        Index(
            f"uq_{table}_open",
            "pos_device_id",
            unique=True,
            postgresql_where=text("to_date IS NULL"),
        ),
        ExcludeConstraint(
            ("pos_device_id", "="),
            (func.daterange(text("from_date"), text("to_date"), "[]"), "&&"),
            name=f"ex_{table}_period",
            using="gist",
        ),
    )


class PosBranchHistory(BaseMixin, Base):
    __tablename__ = "pos_device_branch_history"
    pos_device_id: Mapped[UUID] = mapped_column(ForeignKey("pos_devices.id"), index=True)
    branch_id: Mapped[UUID] = mapped_column(ForeignKey("branches.id"))
    from_date: Mapped[date]
    to_date: Mapped[date | None]
    reason: Mapped[str | None] = mapped_column(String(255))
    __table_args__ = history_constraints(__tablename__)


class PosOwnerHistory(OwnerFields, BaseMixin, Base):
    __tablename__ = "pos_device_owner_history"
    pos_device_id: Mapped[UUID] = mapped_column(ForeignKey("pos_devices.id"), index=True)
    from_date: Mapped[date]
    to_date: Mapped[date | None]
    __table_args__ = history_constraints(__tablename__)


class PosTransaction(BaseMixin, SoftDeleteMixin, Base):
    __tablename__ = "pos_monthly_transactions"
    pos_device_id: Mapped[UUID] = mapped_column(ForeignKey("pos_devices.id"))
    from_date: Mapped[date]
    to_date: Mapped[date]
    transaction_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    transaction_count: Mapped[int] = mapped_column(BigInteger)
    source: Mapped[str] = mapped_column(String(10), default="manual")
    import_id: Mapped[UUID | None] = mapped_column(ForeignKey("import_logs.id"))
    __table_args__ = (
        CheckConstraint("to_date >= from_date AND to_date - from_date <= 365", name="period"),
        CheckConstraint("transaction_amount >= 0 AND transaction_count >= 0", name="values"),
        CheckConstraint("source IN ('manual','import')", name="source"),
        Index("ix_pos_transactions_device_period", "pos_device_id", text("from_date DESC")),
        Index(
            "ix_pos_transactions_period",
            "from_date",
            "to_date",
            "pos_device_id",
            postgresql_where=text("deleted_at IS NULL"),
            postgresql_include=["transaction_amount", "transaction_count"],
        ),
        ExcludeConstraint(
            ("pos_device_id", "="),
            (func.daterange(text("from_date"), text("to_date"), "[]"), "&&"),
            where=text("deleted_at IS NULL"),
            using="gist",
            name="ex_pos_transactions_period",
        ),
    )


class PosPerformanceSettings(Base):
    __tablename__ = "pos_performance_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    lower_threshold: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    upper_threshold: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    policy_version: Mapped[int] = mapped_column(BigInteger, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint(
            "lower_threshold >= 0 AND upper_threshold > lower_threshold", name="thresholds"
        ),
    )


class PosTag(BaseMixin, Base):
    __tablename__ = "pos_tags"
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))


class PosVisit(BaseMixin, Base):
    __tablename__ = "pos_visits"
    pos_device_id: Mapped[UUID] = mapped_column(ForeignKey("pos_devices.id"), index=True)
    branch_id: Mapped[UUID] = mapped_column(ForeignKey("branches.id"))
    selected_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    selected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    assigned_to: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    assigned_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_date: Mapped[date | None]
    instructions: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(25), default="pending_assignment")
    snapshot_from_date: Mapped[date]
    snapshot_to_date: Mapped[date]
    snapshot_amount: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    snapshot_count: Mapped[Decimal | None] = mapped_column(Numeric(30, 0))
    snapshot_no_data: Mapped[bool]
    snapshot_performance: Mapped[str | None] = mapped_column(String(10))
    snapshot_lower_threshold: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    snapshot_upper_threshold: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    snapshot_policy_version: Mapped[int] = mapped_column(BigInteger)
    snapshot_unit: Mapped[str] = mapped_column(String(10), default="rials")
    snapshot_method: Mapped[str] = mapped_column(String(30), default="period_total_amount")
    result: Mapped[str | None] = mapped_column(String(30))
    description: Mapped[str | None] = mapped_column(Text)
    visited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    cancel_reason: Mapped[str | None] = mapped_column(String(255))
    __table_args__ = (
        Index(
            "uq_pos_visits_open",
            "pos_device_id",
            unique=True,
            postgresql_where=text("status IN ('pending_assignment','assigned')"),
        ),
        Index("ix_pos_visits_assignee_state_due", "assigned_to", "status", "due_date"),
        Index("ix_pos_visits_branch_state", "branch_id", "status"),
        CheckConstraint(
            "status IN ('pending_assignment','assigned','completed','cancelled')", name="status"
        ),
        CheckConstraint(
            (
                "status <> 'pending_assignment' OR (assigned_to IS NULL AND "
                "assigned_by IS NULL AND assigned_at IS NULL)"
            ),
            name="pending",
        ),
        CheckConstraint(
            (
                "status NOT IN ('assigned','completed') OR (assigned_to IS NOT "
                "NULL AND assigned_by IS NOT NULL AND assigned_at IS NOT NULL)"
            ),
            name="assigned",
        ),
        CheckConstraint(
            (
                "status <> 'completed' OR (result IS NOT NULL AND visited_at IS "
                "NOT NULL AND completed_at IS NOT NULL)"
            ),
            name="completed",
        ),
        CheckConstraint(
            (
                "status <> 'cancelled' OR (cancelled_at IS NOT NULL AND "
                "cancelled_by IS NOT NULL AND cancel_reason IS NOT NULL AND "
                "length(cancel_reason) > 0)"
            ),
            name="cancelled",
        ),
        CheckConstraint(
            (
                "result IS NULL OR result IN "
                "('visited','owner_unavailable','shop_closed','device_not_found')"
            ),
            name="result",
        ),
        CheckConstraint(
            (
                "snapshot_to_date >= snapshot_from_date AND "
                "snapshot_lower_threshold >= 0 AND snapshot_upper_threshold > "
                "snapshot_lower_threshold"
            ),
            name="snapshot_period_policy",
        ),
        CheckConstraint(
            (
                "(snapshot_no_data AND snapshot_amount IS NULL AND snapshot_count "
                "IS NULL AND snapshot_performance IS NULL) OR (NOT "
                "snapshot_no_data AND snapshot_amount IS NOT NULL AND "
                "snapshot_count IS NOT NULL AND snapshot_performance IS NOT NULL "
                "AND snapshot_amount >= 0 AND snapshot_count >= 0 AND "
                "snapshot_performance IN ('low','normal','high'))"
            ),
            name="snapshot_values",
        ),
        CheckConstraint(
            "snapshot_unit = 'rials' AND snapshot_method = 'period_total_amount'",
            name="snapshot_method",
        ),
    )


class PosVisitTagLink(Base):
    __tablename__ = "pos_visit_tag_links"
    pos_visit_id: Mapped[UUID] = mapped_column(ForeignKey("pos_visits.id"), primary_key=True)
    tag_id: Mapped[UUID] = mapped_column(ForeignKey("pos_tags.id"), primary_key=True)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))


class ImportLog(BaseMixin, Base):
    __tablename__ = "import_logs"
    import_type: Mapped[str] = mapped_column(String(30))
    mode: Mapped[str] = mapped_column(String(20))
    file_name: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(500))
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(25), default="processing")
    period_from: Mapped[date | None]
    period_to: Mapped[date | None]
    total_rows: Mapped[int] = mapped_column(default=0)
    created_count: Mapped[int] = mapped_column(default=0)
    updated_count: Mapped[int] = mapped_column(default=0)
    unchanged_count: Mapped[int] = mapped_column(default=0)
    skipped_count: Mapped[int] = mapped_column(default=0)
    success_count: Mapped[int] = mapped_column(default=0)
    failure_count: Mapped[int] = mapped_column(default=0)
    component_counts: Mapped[dict] = mapped_column(JSONB, default=dict)
    warnings: Mapped[list] = mapped_column(JSONB, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "status IN ('processing','completed','completed_with_errors','failed')", name="status"
        ),
        CheckConstraint(
            "import_type IN ('pos_devices','pos_transactions','pos_combined')", name="type"
        ),
        CheckConstraint(
            "total_rows >= 0 AND success_count >= 0 AND failure_count >= 0", name="counts"
        ),
    )


class ImportRowError(Base):
    __tablename__ = "import_row_errors"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    import_id: Mapped[UUID] = mapped_column(ForeignKey("import_logs.id"), index=True)
    row_number: Mapped[int]
    column_name: Mapped[str | None] = mapped_column(String(100))
    error_code: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(Text)
    raw_data: Mapped[dict] = mapped_column(JSONB)


class Notification(BaseMixin, Base):
    __tablename__ = "notifications"
    recipient_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    channel: Mapped[str] = mapped_column(String(10), default="in_app")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index(
            "ix_notifications_recipient_read_created",
            "recipient_id",
            "is_read",
            text("created_at DESC"),
        ),
    )
