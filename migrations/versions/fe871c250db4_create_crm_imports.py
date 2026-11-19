"""Create CRM import jobs and row outcomes."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "fe871c250db4"
down_revision = "af6ba335cf82"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "crm_imports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("counts", JSONB(), nullable=False),
        sa.Column("warnings", JSONB(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(50)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.CheckConstraint("kind IN ('organization', 'leads')", name="kind"),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'completed', 'completed_with_errors', 'failed')",
            name="status",
        ),
    )
    op.create_index("ix_crm_imports_queue", "crm_imports", ["kind", "status", "created_at", "id"])
    op.create_table(
        "crm_import_rows",
        sa.Column("import_id", sa.Uuid(), sa.ForeignKey("crm_imports.id"), primary_key=True),
        sa.Column("row_number", sa.Integer(), primary_key=True),
        sa.Column("outcome", sa.String(12), nullable=False),
        sa.Column("error_code", sa.String(50)),
        sa.Column("column", sa.String(50)),
        sa.Column("warnings", JSONB(), nullable=False),
        sa.CheckConstraint("outcome IN ('created', 'unchanged', 'failed')", name="outcome"),
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON crm_imports TO crm_runtime")
    op.execute("GRANT SELECT, INSERT ON crm_import_rows TO crm_runtime")


def downgrade():
    op.drop_table("crm_import_rows")
    op.drop_table("crm_imports")
