"""Create core schema"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0a5971fa93bf"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_role", sa.String(length=20), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(
        "ix_audit_logs_actor",
        "audit_logs",
        ["actor_id", sa.literal_column("occurred_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_audit_logs_entity",
        "audit_logs",
        ["entity_type", "entity_id", sa.literal_column("occurred_at DESC")],
        unique=False,
    )
    op.create_table(
        "cities",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cities")),
    )
    op.create_index(
        "uq_cities_name",
        "cities",
        [sa.literal_column("lower(name)")],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "branches",
        sa.Column("city_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["city_id"], ["cities.id"], name=op.f("fk_branches_city_id_cities")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_branches")),
    )
    op.create_index(op.f("ix_branches_city_id"), "branches", ["city_id"], unique=False)
    op.create_index(
        "uq_branches_city_name",
        "branches",
        ["city_id", sa.literal_column("lower(name)")],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_branches_code",
        "branches",
        ["code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "users",
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("mobile", sa.String(length=11), nullable=False),
        sa.Column("national_code", sa.String(length=10), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "must_change_password", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("failed_login_count", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(role = 'supervisor' AND branch_id IS NULL) OR "
            "(role <> 'supervisor' AND branch_id IS NOT NULL)",
            name=op.f("ck_users_branch_by_role"),
        ),
        sa.CheckConstraint(
            "role IN ('supervisor','branch_manager','employee')", name=op.f("ck_users_role")
        ),
        sa.ForeignKeyConstraint(
            ["branch_id"], ["branches.id"], name=op.f("fk_users_branch_id_branches")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_branch_id"), "users", ["branch_id"], unique=False)
    op.create_index(
        "ix_users_name_search",
        "users",
        [sa.literal_column("(first_name || ' ' || last_name) gin_trgm_ops")],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "uq_users_mobile",
        "users",
        ["mobile"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_users_national_code",
        "users",
        ["national_code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND national_code IS NOT NULL"),
    )
    op.create_index(
        "uq_users_one_manager_per_branch",
        "users",
        ["branch_id"],
        unique=True,
        postgresql_where=sa.text("role = 'branch_manager' AND deleted_at IS NULL"),
    )
    op.create_table(
        "login_challenges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("mobile", sa.String(length=11), nullable=False),
        sa.Column("code_digest", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failed_attempts", sa.SmallInteger(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_state", sa.String(length=10), nullable=False),
        sa.CheckConstraint(
            "delivery_state IN ('pending','sent','failed')",
            name=op.f("ck_login_challenges_delivery_state"),
        ),
        sa.CheckConstraint("failed_attempts >= 0", name=op.f("ck_login_challenges_attempts")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_login_challenges_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_login_challenges")),
    )
    op.create_index(
        op.f("ix_login_challenges_user_id"), "login_challenges", ["user_id"], unique=False
    )
    op.create_index(
        "uq_login_challenges_pending_user",
        "login_challenges",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("consumed_at IS NULL AND invalidated_at IS NULL"),
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_refresh_tokens_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
    )
    op.create_index(op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"], unique=False)

    # Add circular actor references only after users exists.
    op.create_foreign_key("fk_cities_created_by_users", "cities", "users", ["created_by"], ["id"])
    op.create_foreign_key("fk_cities_updated_by_users", "cities", "users", ["updated_by"], ["id"])
    op.create_foreign_key("fk_cities_deleted_by_users", "cities", "users", ["deleted_by"], ["id"])
    op.create_foreign_key(
        "fk_branches_created_by_users", "branches", "users", ["created_by"], ["id"]
    )
    op.create_foreign_key(
        "fk_branches_updated_by_users", "branches", "users", ["updated_by"], ["id"]
    )
    op.create_foreign_key(
        "fk_branches_deleted_by_users", "branches", "users", ["deleted_by"], ["id"]
    )
    op.create_foreign_key("fk_users_created_by_users", "users", "users", ["created_by"], ["id"])
    op.create_foreign_key("fk_users_updated_by_users", "users", "users", ["updated_by"], ["id"])
    op.create_foreign_key("fk_users_deleted_by_users", "users", "users", ["deleted_by"], ["id"])
    op.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'crm_runtime') THEN
        GRANT USAGE ON SCHEMA public TO crm_runtime;
        GRANT SELECT, INSERT, UPDATE ON cities, branches, users,
          refresh_tokens, login_challenges TO crm_runtime;
        GRANT SELECT, INSERT ON audit_logs TO crm_runtime;
        GRANT USAGE, SELECT ON SEQUENCE audit_logs_id_seq TO crm_runtime;
        GRANT DELETE ON refresh_tokens, login_challenges TO crm_runtime;
        REVOKE DELETE, TRUNCATE ON cities, branches, users FROM crm_runtime;
        REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM crm_runtime;
      END IF;
    END $$""")


def downgrade():
    op.drop_constraint("fk_cities_created_by_users", "cities", type_="foreignkey")
    op.drop_constraint("fk_cities_updated_by_users", "cities", type_="foreignkey")
    op.drop_constraint("fk_cities_deleted_by_users", "cities", type_="foreignkey")
    op.drop_constraint("fk_branches_created_by_users", "branches", type_="foreignkey")
    op.drop_constraint("fk_branches_updated_by_users", "branches", type_="foreignkey")
    op.drop_constraint("fk_branches_deleted_by_users", "branches", type_="foreignkey")
    op.drop_constraint("fk_users_created_by_users", "users", type_="foreignkey")
    op.drop_constraint("fk_users_updated_by_users", "users", type_="foreignkey")
    op.drop_constraint("fk_users_deleted_by_users", "users", type_="foreignkey")
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f("ix_refresh_tokens_user_id"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index(
        "uq_login_challenges_pending_user",
        table_name="login_challenges",
        postgresql_where=sa.text("consumed_at IS NULL AND invalidated_at IS NULL"),
    )
    op.drop_index(op.f("ix_login_challenges_user_id"), table_name="login_challenges")
    op.drop_table("login_challenges")
    op.drop_index(
        "uq_users_one_manager_per_branch",
        table_name="users",
        postgresql_where=sa.text("role = 'branch_manager' AND deleted_at IS NULL"),
    )
    op.drop_index(
        "uq_users_national_code",
        table_name="users",
        postgresql_where=sa.text("deleted_at IS NULL AND national_code IS NOT NULL"),
    )
    op.drop_index(
        "uq_users_mobile", table_name="users", postgresql_where=sa.text("deleted_at IS NULL")
    )
    op.drop_index("ix_users_name_search", table_name="users", postgresql_using="gin")
    op.drop_index(op.f("ix_users_branch_id"), table_name="users")
    op.drop_table("users")
    op.drop_index(
        "uq_branches_code", table_name="branches", postgresql_where=sa.text("deleted_at IS NULL")
    )
    op.drop_index(
        "uq_branches_city_name",
        table_name="branches",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index(op.f("ix_branches_city_id"), table_name="branches")
    op.drop_table("branches")
    op.drop_index(
        "uq_cities_name", table_name="cities", postgresql_where=sa.text("deleted_at IS NULL")
    )
    op.drop_table("cities")
    op.drop_index("ix_audit_logs_entity", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor", table_name="audit_logs")
    op.drop_table("audit_logs")
    # ### end Alembic commands ###
