"""Allow imported leads to wait for branch assignment."""

import sqlalchemy as sa
from alembic import op

revision = "855385c09c83"
down_revision = "fe871c250db4"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("leads", "branch_id", existing_type=sa.Uuid(), nullable=True)


def downgrade():
    op.alter_column("leads", "branch_id", existing_type=sa.Uuid(), nullable=False)
