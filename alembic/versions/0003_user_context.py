"""Append-only, account-scoped product User Context revisions."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003_user_context"
down_revision = "0002_regional_universes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_context_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("context_payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["app_users.id"], name="fk_context_user"),
        sa.UniqueConstraint("user_id", "revision", name="uq_user_context_revision"),
        sa.CheckConstraint("revision > 0", name="ck_user_context_revision_positive"),
    )
    # Browser/Supabase Data API roles receive no policies; backend access is mediated by API.
    op.execute("ALTER TABLE user_context_revisions ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON user_context_revisions FROM PUBLIC")
    op.execute("""
        CREATE FUNCTION reject_user_context_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Context revisions are immutable' USING ERRCODE = '23000';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER user_context_immutable BEFORE UPDATE OR DELETE
        ON user_context_revisions FOR EACH ROW EXECUTE FUNCTION reject_user_context_mutation()
    """)


def downgrade() -> None:
    op.drop_table("user_context_revisions")
    op.execute("DROP FUNCTION reject_user_context_mutation()")
