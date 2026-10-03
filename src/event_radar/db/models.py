"""Minimal identity persistence; authentication belongs to a later work package."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, text
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
