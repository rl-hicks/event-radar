"""Backend-only account binding and durable delivery intent; no provider or research I/O."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from event_radar.db.models import AppUser, DeliveryBinding, DeliveryChallenge, DeliveryIntent
from event_radar.db.packets import read_packet
from event_radar.db.users import get_or_create_user
from event_radar.models.delivery_authority import PilotDeliveryAuthority


class DeliveryDenied(Exception):
    """Bounded error; never include private destination, challenge or provider data."""


def _lock_user(session: Session, uid: UUID) -> None:
    get_or_create_user(session, uid)
    session.execute(select(AppUser.id).where(AppUser.id == uid).with_for_update()).one()


def challenge(session: Session, uid: UUID, *, now: datetime | None = None) -> str:
    observed = now or datetime.now(UTC)
    _lock_user(session, uid)
    # Issuing a replacement invalidates all outstanding challenges for this account.
    for row in session.scalars(
        select(DeliveryChallenge).where(
            DeliveryChallenge.user_id == uid, DeliveryChallenge.consumed_at.is_(None)
        )
    ):
        row.consumed_at = observed
    token = secrets.token_urlsafe(32)
    session.add(
        DeliveryChallenge(
            id=uuid4(),
            user_id=uid,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            created_at=observed,
            expires_at=observed + timedelta(minutes=10),
        )
    )
    session.flush()
    return token


def accept_private_update(
    session: Session,
    token: str,
    *,
    sender_id: int,
    chat_id: int,
    chat_type: str,
    sender_is_bot: bool,
    now: datetime | None = None,
) -> DeliveryBinding:
    """Trusted inbound adapter ONLY. No public route accepts Telegram updates or IDs.

    Transport authentication must precede this call; synthetic updates exercise it offline.
    The bearer challenge identifies its owning account; there is no caller account selector.
    """
    observed = now or datetime.now(UTC)
    if (
        chat_type != "private"
        or sender_is_bot
        or type(sender_id) is not int
        or type(chat_id) is not int
        or not 0 < sender_id == chat_id < 2**52
        or len(token) != 43
    ):
        raise DeliveryDenied
    hashed = hashlib.sha256(token.encode()).hexdigest()
    row = session.scalar(select(DeliveryChallenge).where(DeliveryChallenge.token_hash == hashed))
    if row is None:
        raise DeliveryDenied
    _lock_user(session, row.user_id)
    session.refresh(row, with_for_update=True)
    if row.consumed_at is not None or not row.created_at <= observed < row.expires_at:
        raise DeliveryDenied
    destination = str(chat_id)
    # Serialize races involving the same destination across different accounts.
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": "telegram:" + destination},
    )
    foreign = session.scalar(
        select(DeliveryBinding.id)
        .where(
            DeliveryBinding.channel == "telegram",
            DeliveryBinding.destination == destination,
            DeliveryBinding.user_id != row.user_id,
        )
        .limit(1)
    )
    if foreign:
        raise DeliveryDenied
    latest = (
        session.scalar(
            select(func.max(DeliveryBinding.revision)).where(
                DeliveryBinding.user_id == row.user_id, DeliveryBinding.channel == "telegram"
            )
        )
        or 0
    )
    for old in session.scalars(
        select(DeliveryBinding)
        .where(
            DeliveryBinding.user_id == row.user_id,
            DeliveryBinding.channel == "telegram",
            DeliveryBinding.status == "active",
        )
        .with_for_update()
    ):
        old.status, old.revoked_at, old.consent = "revoked", observed, False
    session.flush()
    binding = DeliveryBinding(
        id=uuid4(),
        user_id=row.user_id,
        channel="telegram",
        revision=latest + 1,
        destination=destination,
        status="active",
        consent=True,
        verified_at=observed,
    )
    row.consumed_at = observed
    session.add(binding)
    session.flush()
    return binding


def revoke(session: Session, uid: UUID, binding_id: UUID) -> None:
    _lock_user(session, uid)
    binding = session.scalar(
        select(DeliveryBinding)
        .where(DeliveryBinding.id == binding_id, DeliveryBinding.user_id == uid)
        .with_for_update()
    )
    if binding is None:
        raise DeliveryDenied
    if binding.status == "revoked":
        return
    binding.status, binding.consent, binding.revoked_at = "revoked", False, datetime.now(UTC)
    for row in session.scalars(
        select(DeliveryChallenge).where(
            DeliveryChallenge.user_id == uid, DeliveryChallenge.consumed_at.is_(None)
        )
    ):
        row.consumed_at = datetime.now(UTC)
    session.flush()


def queue_delivery(
    session: Session,
    uid: UUID,
    packet_id: UUID,
    binding_id: UUID,
    channel: str,
    *,
    development: bool = False,
    approval: PilotDeliveryAuthority | None = None,
) -> UUID:
    # No commercial entitlement implementation exists. Public/live use fails closed.
    if channel != "telegram" or not (
        development
        or (approval and approval.permits(uid, packet_id, binding_id, datetime.now(UTC)))
    ):
        raise DeliveryDenied
    _lock_user(session, uid)
    binding = session.scalar(
        select(DeliveryBinding)
        .where(DeliveryBinding.id == binding_id, DeliveryBinding.user_id == uid)
        .with_for_update()
    )
    if (
        binding is None
        or binding.status != "active"
        or not binding.consent
        or binding.channel != channel
    ):
        raise DeliveryDenied
    packet = read_packet(session, uid, packet_id)
    if packet is None or packet.status not in ("success", "partial"):
        raise DeliveryDenied
    # Partial packets are eligible only with their explicit quality labels preserved.
    identifier = uuid4()
    now = datetime.now(UTC)
    result = session.execute(
        insert(DeliveryIntent)
        .values(
            id=identifier,
            user_id=uid,
            packet_id=packet_id,
            binding_id=binding_id,
            channel=channel,
            status="pending",
            attempts=0,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(constraint="uq_delivery_intent")
        .returning(DeliveryIntent.id)
    ).scalar()
    if result:
        return result
    return session.scalars(
        select(DeliveryIntent.id).where(
            DeliveryIntent.packet_id == packet_id,
            DeliveryIntent.channel == channel,
            DeliveryIntent.binding_id == binding_id,
            DeliveryIntent.user_id == uid,
        )
    ).one()
