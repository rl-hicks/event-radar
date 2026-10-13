"""Backend persistence models for product identity and shared regional intelligence."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
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


class UserContextRevision(Base):
    """Append-only private history. Highest revision is the active context."""

    __tablename__ = "user_context_revisions"
    __table_args__ = (
        UniqueConstraint("user_id", "revision", name="uq_user_context_revision"),
        UniqueConstraint("id", "user_id", name="uq_context_owned_id"),
        CheckConstraint("revision > 0", name="ck_user_context_revision_positive"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("app_users.id", name="fk_context_user"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    context_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class CurationJob(Base):
    """One bounded call per full input identity; failed/abandoned claims are terminal."""

    __tablename__ = "curation_jobs"
    __table_args__ = (
        UniqueConstraint("identity", name="uq_curation_identity"),
        UniqueConstraint(
            "id", "user_id", "context_revision_id", "snapshot_id", name="uq_curation_packet_binding"
        ),
        ForeignKeyConstraint(
            ["context_revision_id", "user_id"],
            ["user_context_revisions.id", "user_context_revisions.user_id"],
            name="fk_curation_owned_context",
        ),
        CheckConstraint(
            "(status = 'running' AND finished_at IS NULL AND failure_code IS NULL) OR "
            "(status IN ('success', 'partial') AND finished_at IS NOT NULL "
            "AND failure_code IS NULL) OR "
            "(status = 'failed' AND finished_at IS NOT NULL AND failure_code IS NOT NULL)",
            name="ck_curation_state",
        ),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    identity: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("app_users.id"), nullable=False
    )
    context_revision_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    context_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("regional_universe_snapshots.id"), nullable=False
    )
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    usage_payload: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)


class WeekendPacketRecord(Base):
    __tablename__ = "weekend_packets"
    __table_args__ = (
        UniqueConstraint("execution_id", name="uq_packet_execution"),
        UniqueConstraint("id", "user_id", name="uq_packet_owner"),
        ForeignKeyConstraint(
            ["execution_id", "user_id", "context_revision_id", "snapshot_id"],
            [
                "curation_jobs.id",
                "curation_jobs.user_id",
                "curation_jobs.context_revision_id",
                "curation_jobs.snapshot_id",
            ],
            name="fk_packet_execution_binding",
        ),
        Index("ix_packet_owner_created", "user_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    execution_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    context_revision_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    packet_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DeliveryBinding(Base):
    """A revision is a new row; destinations never silently move between accounts."""

    __tablename__ = "delivery_bindings"
    __table_args__ = (
        UniqueConstraint("user_id", "channel", "revision", name="uq_binding_revision"),
        UniqueConstraint("id", "user_id", name="uq_binding_owner"),
        CheckConstraint("channel IN ('telegram','email')", name="ck_binding_channel"),
        CheckConstraint("status IN ('active','revoked')", name="ck_binding_status"),
        CheckConstraint("revision > 0", name="ck_binding_revision"),
        Index(
            "uq_binding_active_user",
            "user_id",
            "channel",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index(
            "uq_binding_active_destination",
            "channel",
            "destination",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("app_users.id"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    destination: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    consent: Mapped[bool] = mapped_column(Boolean, nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DeliveryChallenge(Base):
    __tablename__ = "delivery_challenges"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_challenge_hash"),
        CheckConstraint("expires_at > created_at", name="ck_challenge_expiry"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("app_users.id"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DeliveryIntent(Base):
    __tablename__ = "delivery_intents"
    __table_args__ = (
        UniqueConstraint("packet_id", "channel", "binding_id", name="uq_delivery_intent"),
        ForeignKeyConstraint(
            ["binding_id", "user_id"],
            ["delivery_bindings.id", "delivery_bindings.user_id"],
            name="fk_delivery_owned_binding",
        ),
        ForeignKeyConstraint(
            ["packet_id", "user_id"],
            ["weekend_packets.id", "weekend_packets.user_id"],
            name="fk_delivery_owned_packet",
        ),
        CheckConstraint("channel IN ('telegram','email')", name="ck_delivery_channel"),
        CheckConstraint(
            "status IN ('pending','sending','sent','failed','ambiguous','revoked')",
            name="ck_delivery_status",
        ),
        CheckConstraint("attempts >= 0 AND attempts <= 3", name="ck_delivery_attempts"),
        CheckConstraint(
            "failure_code IS NULL OR failure_code IN "
            "('rejected','transport_unknown','invalid_response','revoked','packet_unavailable')",
            name="ck_delivery_failure",
        ),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    packet_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    binding_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DeliveryAttempt(Base):
    __tablename__ = "delivery_attempts"
    __table_args__ = (
        UniqueConstraint("intent_id", "number", name="uq_delivery_attempt"),
        CheckConstraint("number BETWEEN 1 AND 3", name="ck_attempt_number"),
        CheckConstraint(
            "status IN ('sending','sent','failed','ambiguous')", name="ck_attempt_status"
        ),
        CheckConstraint(
            "failure_code IS NULL OR failure_code IN "
            "('rejected','transport_unknown','invalid_response')",
            name="ck_attempt_failure",
        ),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    intent_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("delivery_intents.id"), nullable=False
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
