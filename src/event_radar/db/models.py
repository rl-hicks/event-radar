"""Backend persistence models for product identity and shared regional intelligence."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from event_radar.db.base import Base


class AppUser(Base):
    __tablename__ = "app_users"

    # The caller supplies the future authenticated identity; no random DB default.
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    # Both timestamps initialize on INSERT. Future writers must explicitly update
    # updated_at; there is deliberately no trigger or ORM onupdate policy yet.


class RegionalUniverse(Base):
    """Stable logical region/weekend/research-policy identity."""

    __tablename__ = "regional_universes"
    __table_args__ = (
        UniqueConstraint(
            "region_id",
            "weekend_friday",
            "research_policy_version",
            name="uq_regional_universe_logical_identity",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    region_id: Mapped[str] = mapped_column(String(120), nullable=False)
    weekend_friday: Mapped[date] = mapped_column(Date, nullable=False)
    research_policy_version: Mapped[str] = mapped_column(String(120), nullable=False)
    current_snapshot_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "regional_universe_snapshots.id",
            name="fk_regional_universes_current_snapshot",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class RegionalUniverseSnapshot(Base):
    """Immutable validated universe snapshot for one logical identity."""

    __tablename__ = "regional_universe_snapshots"
    __table_args__ = (
        CheckConstraint(
            "quality_status IN ('success', 'partial')",
            name="ck_regional_snapshot_quality_status",
        ),
        UniqueConstraint(
            "universe_id",
            "content_hash",
            name="uq_regional_snapshot_content",
        ),
        Index(
            "ix_regional_snapshots_universe_created",
            "universe_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    universe_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("regional_universes.id", name="fk_regional_snapshots_universe"),
        nullable=False,
    )
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quality_status: Mapped[str] = mapped_column(String(16), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    universe_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    discovery_summary: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class RegionalResearchRun(Base):
    """One execution attempt against a stable regional-universe identity."""

    __tablename__ = "regional_research_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'success', 'partial', 'failed')",
            name="ck_regional_run_status",
        ),
        CheckConstraint(
            "("
            "(status = 'running' AND finished_at IS NULL AND snapshot_id IS NULL) OR "
            "(status IN ('success', 'partial') AND finished_at IS NOT NULL "
            "AND snapshot_id IS NOT NULL) OR "
            "(status = 'failed' AND finished_at IS NOT NULL AND snapshot_id IS NULL "
            "AND failure_code IS NOT NULL)"
            ")",
            name="ck_regional_run_state_shape",
        ),
        Index(
            "ix_regional_runs_universe_started",
            "universe_id",
            "started_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    universe_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("regional_universes.id", name="fk_regional_runs_universe"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    snapshot_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("regional_universe_snapshots.id", name="fk_regional_runs_snapshot"),
        nullable=True,
    )
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    diagnostics_payload: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    discovery_summary: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
