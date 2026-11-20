"""Persist lead import retry state."""

import sqlalchemy as sa
from alembic import op

revision = "efd97ae450e3"
down_revision = "855385c09c83"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "crm_imports",
        sa.Column("retry_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("crm_imports", sa.Column("next_attempt_at", sa.DateTime(timezone=True)))


def downgrade():
    op.drop_column("crm_imports", "next_attempt_at")
    op.drop_column("crm_imports", "retry_count")
