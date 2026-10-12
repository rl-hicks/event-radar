"""Persist regional universe snapshots and research attempts.

Revision ID: 0002_regional_universes
Revises: 0001_app_users
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_regional_universes"
down_revision: str | None = "0001_app_users"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "regional_universes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("region_id", sa.String(length=120), nullable=False),
        sa.Column("weekend_friday", sa.Date(), nullable=False),
        sa.Column("research_policy_version", sa.String(length=120), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "region_id",
            "weekend_friday",
            "research_policy_version",
            name="uq_regional_universe_logical_identity",
        ),
    )

    op.create_table(
        "regional_universe_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("universe_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quality_status", sa.String(length=16), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("universe_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("discovery_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "quality_status IN ('success', 'partial')",
            name="ck_regional_snapshot_quality_status",
        ),
        sa.ForeignKeyConstraint(
            ["universe_id"],
            ["regional_universes.id"],
            name="fk_regional_snapshots_universe",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "universe_id",
            "content_hash",
            name="uq_regional_snapshot_content",
        ),
    )
    op.create_index(
        "ix_regional_snapshots_universe_created",
        "regional_universe_snapshots",
        ["universe_id", "created_at"],
        unique=False,
    )

    op.add_column(
        "regional_universes",
        sa.Column("current_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_regional_universes_current_snapshot",
        "regional_universes",
        "regional_universe_snapshots",
        ["current_snapshot_id"],
        ["id"],
    )

    op.create_table(
        "regional_research_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("universe_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("requested_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("diagnostics_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("discovery_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'success', 'partial', 'failed')",
            name="ck_regional_run_status",
        ),
        sa.CheckConstraint(
            "("
            "(status = 'running' AND finished_at IS NULL AND snapshot_id IS NULL) OR "
            "(status IN ('success', 'partial') AND finished_at IS NOT NULL "
            "AND snapshot_id IS NOT NULL) OR "
            "(status = 'failed' AND finished_at IS NOT NULL AND snapshot_id IS NULL "
            "AND failure_code IS NOT NULL)"
            ")",
            name="ck_regional_run_state_shape",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["regional_universe_snapshots.id"],
            name="fk_regional_runs_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["universe_id"],
            ["regional_universes.id"],
            name="fk_regional_runs_universe",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_regional_runs_universe_started",
        "regional_research_runs",
        ["universe_id", "started_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_regional_runs_universe_started", table_name="regional_research_runs")
    op.drop_table("regional_research_runs")

    op.drop_constraint(
        "fk_regional_universes_current_snapshot",
        "regional_universes",
        type_="foreignkey",
    )
    op.drop_column("regional_universes", "current_snapshot_id")

    op.drop_index(
        "ix_regional_snapshots_universe_created",
        table_name="regional_universe_snapshots",
    )
    op.drop_table("regional_universe_snapshots")
    op.drop_table("regional_universes")
