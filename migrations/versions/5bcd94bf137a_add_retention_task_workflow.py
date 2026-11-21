"""Open pending retention tasks and store visit completion details."""

import sqlalchemy as sa
from alembic import op

revision = "5bcd94bf137a"
down_revision = "efd97ae450e3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("retention_tasks", sa.Column("visit_date", sa.Date()))
    op.add_column("retention_tasks", sa.Column("result", sa.String(30)))
    op.add_column("retention_tasks", sa.Column("notes", sa.Text()))
    op.add_column("retention_tasks", sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.add_column("retention_tasks", sa.Column("completed_by", sa.Uuid()))
    op.create_foreign_key(
        op.f("fk_retention_tasks_completed_by_users"),
        "retention_tasks",
        "users",
        ["completed_by"],
        ["id"],
    )
    op.execute("UPDATE retention_schedules SET requires_approval = false WHERE requires_approval")
    op.execute("UPDATE retention_tasks SET status = 'open' WHERE status = 'pending_approval'")
    op.drop_constraint(op.f("ck_retention_tasks_status"), "retention_tasks", type_="check")
    op.create_check_constraint(
        op.f("ck_retention_tasks_status"),
        "retention_tasks",
        "status IN ('open','completed','cancelled')",
    )


def downgrade():
    op.drop_constraint(op.f("ck_retention_tasks_status"), "retention_tasks", type_="check")
    op.create_check_constraint(
        op.f("ck_retention_tasks_status"),
        "retention_tasks",
        "status IN ('pending_approval','open','completed','cancelled')",
    )
    op.drop_constraint(
        op.f("fk_retention_tasks_completed_by_users"),
        "retention_tasks",
        type_="foreignkey",
    )
    for column in ("completed_by", "completed_at", "notes", "result", "visit_date"):
        op.drop_column("retention_tasks", column)
