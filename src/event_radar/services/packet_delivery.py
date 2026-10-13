"""Delivery-only renderer and fake-only dispatcher. No network client or credentials."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from event_radar.db.delivery import DeliveryDenied
from event_radar.db.models import DeliveryAttempt, DeliveryBinding, DeliveryIntent
from event_radar.db.packets import read_packet
from event_radar.models.delivery_authority import PilotDeliveryAuthority
from event_radar.models.weekend_packet import WeekendPacket
from event_radar.services.telegram_transport import TelegramHTTPTransport


@dataclass
class FakeTelegramTransport:
    """Deterministic transport outcomes; stores synthetic messages in memory only."""

    outcomes: list[str] = field(default_factory=lambda: ["success"])
    messages: list[str] = field(default_factory=list)

    def send(self, destination: str, message: str) -> str:
        self.messages.append(message)
        return self.outcomes.pop(0) if self.outcomes else "success"


def render_telegram(packet: WeekendPacket) -> list[str]:
    lines = [
        f"Weekend Packet · {packet.weekend_friday} · {packet.region_id}",
        f"Research as of {packet.research_as_of.isoformat()}",
        f"Research: {packet.research_quality}; curation: {packet.curation_status}",
        "Recommendations do not confirm availability or booking. Verify source terms.",
        f"Preferences revision: {packet.context_revision_id}",
    ]
    for index, recommendation in enumerate(packet.recommendations, 1):
        facts = recommendation.facts
        lines += [
            f"{index}. {facts.title}",
            ", ".join(
                x for x in (facts.location.venue, facts.location.city, facts.location.county) if x
            ),
            recommendation.rationale,
            "Tradeoffs: " + (", ".join(recommendation.judgment.tradeoffs) or "None specified"),
            "Friction: " + recommendation.judgment.friction.replace("_", " "),
        ]
        if not facts.occurrences:
            lines.append("No scheduled time established; verify access and opening times.")
        for occurrence in facts.occurrences:
            lines += [
                f"Time: {occurrence.start.isoformat()} to "
                f"{occurrence.end.isoformat() if occurrence.end else 'end unknown'}",
                "Location: "
                + ", ".join(x for x in (occurrence.location.venue, occurrence.location.city) if x),
                "Price: " + occurrence.price.state,
            ]
            for quote in occurrence.price.quotes:
                lines.append(
                    f"{quote.currency or ''} {quote.minimum if quote.minimum is not None else '?'}–"
                    f"{quote.maximum if quote.maximum is not None else '?'} {quote.details or ''}"
                )
            lines.append(
                f"Attendance: {occurrence.available.state}; "
                f"source value: {occurrence.available.value}"
            )
        lines.append(f"Access: {facts.access_open.state}; source value: {facts.access_open.value}")
        if facts.route:
            lines.append(
                f"Route: {facts.route.distance_miles} miles; "
                f"gain {facts.route.elevation_gain_ft} ft; "
                f"{facts.route.route_description or 'details unknown'}"
            )
        lines += ["Unknown: " + value for value in recommendation.important_unknowns]
        lines += ["Source: " + str(evidence.url) for evidence in facts.evidence]
    if not packet.recommendations:
        lines.append("No recommendations in this packet.")
    # Plain text, no Markdown/HTML parse mode. UTF-16 accounting also bounds astral symbols.
    chunks, chunk, size = [], "", 0
    for character in "\n".join(lines):
        units = len(character.encode("utf-16-le")) // 2
        if size + units > 3900:
            chunks.append(chunk)
            chunk, size = "", 0
        chunk += character
        size += units
    if chunk:
        chunks.append(chunk)
    return chunks


def dispatch_fake(
    engine: Engine,
    intent_id: UUID,
    transport: FakeTelegramTransport,
    *,
    development: bool = False,
    retry: bool = False,
) -> str:
    if not development or type(transport) is not FakeTelegramTransport:
        raise DeliveryDenied
    return dispatch_delivery(engine, intent_id, transport, development=True, retry=retry)


def dispatch_delivery(
    engine: Engine,
    intent_id: UUID,
    transport: FakeTelegramTransport | TelegramHTTPTransport,
    *,
    development: bool = False,
    retry: bool = False,
    approval: PilotDeliveryAuthority | None = None,
) -> str:
    fake = type(transport) is FakeTelegramTransport and development
    with Session(engine) as session, session.begin():
        intent = session.scalar(
            select(DeliveryIntent).where(DeliveryIntent.id == intent_id).with_for_update()
        )
        if intent is None or not (
            fake
            or (
                type(transport) is TelegramHTTPTransport
                and approval
                and approval.permits(
                    intent.user_id, intent.packet_id, intent.binding_id, datetime.now(UTC)
                )
            )
        ):
            raise DeliveryDenied
        if intent.status != "pending" and not (
            retry and intent.status == "failed" and intent.attempts < 3
        ):
            return intent.status
        binding = session.get(DeliveryBinding, intent.binding_id)
        if (
            binding is None
            or binding.user_id != intent.user_id
            or binding.channel != "telegram"
            or binding.status != "active"
            or not binding.consent
        ):
            intent.status, intent.failure_code = "revoked", "revoked"
            return "revoked"
        try:
            packet = read_packet(session, intent.user_id, intent.packet_id)
            if packet is None:
                raise DeliveryDenied
            messages = render_telegram(packet)
            if not 1 <= len(messages) <= 16:
                raise DeliveryDenied
        except Exception:
            intent.status, intent.failure_code = "failed", "packet_unavailable"
            return "failed"
        intent.status, intent.failure_code = "sending", None
        intent.attempts += 1
        intent.updated_at = datetime.now(UTC)
        attempt_id = uuid4()
        session.add(
            DeliveryAttempt(
                id=attempt_id,
                intent_id=intent.id,
                number=intent.attempts,
                status="sending",
                started_at=intent.updated_at,
            )
        )
        binding_id, uid, pid = binding.id, intent.user_id, intent.packet_id
    # Durable claim precedes transport. A crash leaves sending; never auto-redispatch.
    status: Literal["sent", "failed", "ambiguous"] = "sent"
    code = None
    revoked = False
    for index, message in enumerate(messages):
        # No Session/transaction or DB lock remains open across any network I/O.
        with Session(engine) as session:
            binding = session.get(DeliveryBinding, binding_id)
            valid = (
                binding is not None
                and binding.status == "active"
                and binding.consent
                and binding.user_id == uid
                and binding.channel == "telegram"
            )
            destination = binding.destination if binding else ""
        if not valid or not (
            fake or (approval and approval.permits(uid, pid, binding_id, datetime.now(UTC)))
        ):
            revoked = index == 0
            status, code = (
                ("failed", "rejected") if index == 0 else ("ambiguous", "transport_unknown")
            )
            break
        try:
            outcome = transport.send(destination, message)
        except Exception:
            outcome = "ambiguous"
        if outcome != "success":
            status = "failed" if outcome == "rejected" and index == 0 else "ambiguous"
            code = (
                "rejected"
                if outcome == "rejected"
                else "transport_unknown"
                if outcome == "ambiguous"
                else "invalid_response"
            )
            break
    with Session(engine) as session, session.begin():
        intent = session.get(DeliveryIntent, intent_id)
        attempt = session.get(DeliveryAttempt, attempt_id)
        assert intent is not None and attempt is not None
        intent.status = "revoked" if revoked else status
        intent.failure_code = "revoked" if revoked else code
        attempt.status, attempt.failure_code = status, code
        attempt.finished_at = intent.updated_at = datetime.now(UTC)
        return intent.status
