"""Trusted operator approval for one noncommercial pilot packet, never a user entitlement."""

from datetime import datetime, timedelta
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from event_radar.models.product_context import ContextModel


class PilotDeliveryAuthority(ContextModel):
    approval_reference: str = Field(min_length=1, max_length=200)
    user_id: UUID
    packet_id: UUID
    binding_id: UUID
    issued_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def bounded(self) -> "PilotDeliveryAuthority":
        if not timedelta(0) < self.expires_at - self.issued_at <= timedelta(hours=1):
            raise ValueError("Pilot approval must expire within one hour.")
        return self

    def permits(self, user: UUID, packet: UUID, binding: UUID, now: datetime) -> bool:
        return (user, packet, binding) == (
            self.user_id,
            self.packet_id,
            self.binding_id,
        ) and self.issued_at <= now < self.expires_at
