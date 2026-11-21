from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BaseMixin


class Occupation(BaseMixin, Base):
    __tablename__ = "occupations"

    name: Mapped[str] = mapped_column(String(100))
    name_key: Mapped[str] = mapped_column(String(300), unique=True)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))


class BankingProduct(BaseMixin, Base):
    __tablename__ = "banking_products"

    name: Mapped[str] = mapped_column(String(100))
    code: Mapped[str] = mapped_column(String(50), unique=True)
    score_value: Mapped[int]
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    __table_args__ = (CheckConstraint("score_value >= 0", name="score_value"),)


class Lead(BaseMixin, Base):
    __tablename__ = "leads"

    branch_id: Mapped[UUID | None] = mapped_column(ForeignKey("branches.id"), index=True)
    city_id: Mapped[UUID] = mapped_column(ForeignKey("cities.id"), index=True)
    occupation_id: Mapped[UUID | None] = mapped_column(ForeignKey("occupations.id"), index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    mobile: Mapped[str] = mapped_column(String(11), unique=True)
    national_code: Mapped[str | None] = mapped_column(String(10), unique=True)
    address: Mapped[str | None] = mapped_column(Text)
    referrer: Mapped[str | None] = mapped_column(String(200))
    additional_info: Mapped[str | None] = mapped_column(Text)
    is_customer: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))


class Campaign(BaseMixin, Base):
    __tablename__ = "campaigns"

    title: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[date]
    end_date: Mapped[date]
    status: Mapped[str] = mapped_column(String(10), default="draft", server_default="draft")
    include_customers: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="dates"),
        CheckConstraint("status IN ('draft','active','closed')", name="status"),
    )


class CampaignLead(BaseMixin, Base):
    __tablename__ = "campaign_leads"

    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("campaigns.id"))
    lead_id: Mapped[UUID] = mapped_column(ForeignKey("leads.id"), index=True)
    branch_id: Mapped[UUID] = mapped_column(ForeignKey("branches.id"))
    assigned_to_branch_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    selected: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    reserved: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    status: Mapped[str] = mapped_column(String(10), default="available", server_default="available")
    locked_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("campaign_id", "lead_id"),
        CheckConstraint("status IN ('available','locked','completed')", name="status"),
        CheckConstraint("NOT reserved OR selected", name="reservation_selection"),
        CheckConstraint(
            "(status = 'available' AND locked_by IS NULL AND locked_at IS NULL"
            " AND completed_at IS NULL) OR "
            "(status IN ('locked','completed') AND locked_by IS NOT NULL AND locked_at IS NOT NULL"
            " AND (status = 'completed') = (completed_at IS NOT NULL))",
            name="assignment",
        ),
        Index(
            "uq_campaign_leads_reservation",
            "lead_id",
            unique=True,
            postgresql_where=text("reserved"),
        ),
        Index("ix_campaign_leads_branch_work", "campaign_id", "branch_id", "status"),
        Index("ix_campaign_leads_employee_work", "campaign_id", "locked_by"),
    )


class CampaignQuotaOverride(BaseMixin, Base):
    __tablename__ = "campaign_quota_overrides"

    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("campaigns.id"))
    employee_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    quota: Mapped[int]
    reason: Mapped[str] = mapped_column(String(255))
    __table_args__ = (
        UniqueConstraint("campaign_id", "employee_id"),
        CheckConstraint("quota >= 0", name="quota"),
    )


VISIT_RESULT_CHECK = "result IN ('pending','interested','not_interested','no_response')"


class VisitFields:
    employee_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    visit_date: Mapped[date]
    result: Mapped[str] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(Text)
    additional_info: Mapped[str | None] = mapped_column(Text)


class CampaignVisit(VisitFields, BaseMixin, Base):
    __tablename__ = "visits"

    campaign_lead_id: Mapped[UUID] = mapped_column(ForeignKey("campaign_leads.id"), unique=True)
    visit_count: Mapped[int]
    last_visited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(VISIT_RESULT_CHECK, name="result"),
        CheckConstraint("visit_count > 0", name="visit_count"),
    )


class VisitAttempt(VisitFields, BaseMixin, Base):
    __tablename__ = "visit_attempts"

    visit_id: Mapped[UUID] = mapped_column(ForeignKey("visits.id"))
    attempt_no: Mapped[int]
    __table_args__ = (
        UniqueConstraint("visit_id", "attempt_no"),
        CheckConstraint(VISIT_RESULT_CHECK, name="result"),
        CheckConstraint("attempt_no > 0", name="attempt_no"),
    )


class CustomerDraft(BaseMixin, Base):
    __tablename__ = "customer_drafts"

    lead_id: Mapped[UUID] = mapped_column(ForeignKey("leads.id"), unique=True)
    profile: Mapped[dict] = mapped_column(JSONB)
    entered_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))


class Customer(BaseMixin, Base):
    __tablename__ = "customers"

    lead_id: Mapped[UUID] = mapped_column(ForeignKey("leads.id"), unique=True)
    branch_id: Mapped[UUID] = mapped_column(ForeignKey("branches.id"), index=True)
    city_id: Mapped[UUID] = mapped_column(ForeignKey("cities.id"), index=True)
    acquired_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    first_sale_id: Mapped[UUID] = mapped_column(
        ForeignKey("product_sales.id", use_alter=True), unique=True
    )
    customer_code: Mapped[str] = mapped_column(String(50), unique=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(20))
    address: Mapped[str] = mapped_column(Text)
    national_code: Mapped[str | None] = mapped_column(String(10))
    customer_since: Mapped[date]
    converted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProductSale(BaseMixin, Base):
    __tablename__ = "product_sales"

    lead_id: Mapped[UUID] = mapped_column(ForeignKey("leads.id"), index=True)
    customer_id: Mapped[UUID | None] = mapped_column(ForeignKey("customers.id"), index=True)
    visit_id: Mapped[UUID] = mapped_column(ForeignKey("visits.id"), index=True)
    banking_product_id: Mapped[UUID] = mapped_column(ForeignKey("banking_products.id"))
    employee_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    account_number: Mapped[str] = mapped_column(String(100))
    proof_text: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="draft", server_default="draft")
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(String(500))
    resubmit_count: Mapped[int] = mapped_column(default=0, server_default="0")
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','submitted','approved','rejected','withdrawn')", name="status"
        ),
        CheckConstraint("status <> 'rejected' OR rejection_reason IS NOT NULL", name="rejection"),
        Index(
            "uq_product_sales_live_product",
            "lead_id",
            "banking_product_id",
            unique=True,
            postgresql_where=text("status <> 'withdrawn'"),
        ),
        Index("ix_product_sales_queue", "status", "last_submitted_at"),
        Index("ix_product_sales_employee", "employee_id", "status"),
    )


class SaleSubmission(BaseMixin, Base):
    __tablename__ = "sale_submissions"

    sale_id: Mapped[UUID] = mapped_column(ForeignKey("product_sales.id"))
    revision: Mapped[int]
    profile: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    banking_product_id: Mapped[UUID] = mapped_column(ForeignKey("banking_products.id"))
    account_number: Mapped[str] = mapped_column(String(100))
    proof_text: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("sale_id", "revision"),)


class SaleDecision(BaseMixin, Base):
    __tablename__ = "sale_decisions"

    submission_id: Mapped[UUID] = mapped_column(ForeignKey("sale_submissions.id"), unique=True)
    status: Mapped[str] = mapped_column(String(10))
    reason: Mapped[str | None] = mapped_column(String(500))
    decided_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "(status = 'approved' AND reason IS NULL)"
            " OR (status = 'rejected' AND reason IS NOT NULL)",
            name="decision",
        ),
    )


class CustomerProduct(BaseMixin, Base):
    __tablename__ = "customer_products"

    customer_id: Mapped[UUID] = mapped_column(ForeignKey("customers.id"))
    banking_product_id: Mapped[UUID] = mapped_column(ForeignKey("banking_products.id"), index=True)
    source_sale_id: Mapped[UUID] = mapped_column(ForeignKey("product_sales.id"), unique=True)
    account_number: Mapped[str] = mapped_column(String(100))
    started_at: Mapped[date]
    __table_args__ = (UniqueConstraint("customer_id", "banking_product_id"),)


class RetentionSchedule(BaseMixin, Base):
    __tablename__ = "retention_schedules"

    label: Mapped[str] = mapped_column(String(100))
    days_after_conversion: Mapped[int]
    requires_approval: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    __table_args__ = (
        CheckConstraint("days_after_conversion > 0", name="offset"),
        Index(
            "uq_retention_schedules_active_offset",
            "days_after_conversion",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )


class RetentionTask(BaseMixin, Base):
    __tablename__ = "retention_tasks"

    customer_id: Mapped[UUID] = mapped_column(ForeignKey("customers.id"))
    retention_schedule_id: Mapped[UUID] = mapped_column(ForeignKey("retention_schedules.id"))
    assigned_to: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    due_date: Mapped[date]
    status: Mapped[str] = mapped_column(String(20))
    visit_date: Mapped[date | None]
    result: Mapped[str | None] = mapped_column(String(30))
    notes: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    __table_args__ = (
        UniqueConstraint("customer_id", "retention_schedule_id"),
        CheckConstraint("status IN ('open','completed','cancelled')", name="status"),
        Index("ix_retention_tasks_assignment", "assigned_to", "status", "due_date"),
    )


class ScoreTransaction(BaseMixin, Base):
    __tablename__ = "score_transactions"

    employee_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    source_type: Mapped[str] = mapped_column(String(20), default="product_sale")
    source_id: Mapped[UUID]
    points: Mapped[int]
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("source_type", "source_id"),
        CheckConstraint("source_type IN ('product_sale','retention_task')", name="source_type"),
        Index("ix_score_transactions_employee_time", "employee_id", "occurred_at"),
    )
