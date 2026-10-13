"""Synthetic PostgreSQL proof; external HTTP is forbidden throughout."""

from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from event_radar.api.app import create_app
from event_radar.auth import identity
from event_radar.db.contexts import write_context
from event_radar.db.current_packet import current_friday, read_current_packet
from event_radar.db.delivery import (
    DeliveryDenied,
    accept_private_update,
    challenge,
    queue_delivery,
    revoke,
)
from event_radar.db.models import (
    CurationJob,
    DeliveryAttempt,
    DeliveryBinding,
    DeliveryChallenge,
    DeliveryIntent,
)
from event_radar.db.packets import PacketCorrupt, read_packet
from event_radar.models.product_context import ProductUserContext
from event_radar.services.packet_delivery import (
    FakeTelegramTransport,
    dispatch_fake,
    render_telegram,
)
from event_radar.services.packet_generation import generate_packet
from event_radar.services.personalized_curation import DeterministicCurationProvider
from tests.auth_helpers import CONFIG, signed, signing_fixture
from tests.test_development_evidence import regional_rows
from tests.test_weekend_packets import OUTDOOR, no_external_calls
from tests.test_weekend_packets_integration import setup

__all__ = ["setup", "no_external_calls"]


def bind(engine, uid, now, destination=123):
    with Session(engine) as s, s.begin():
        token = challenge(s, uid, now=now)
    with Session(engine) as s, s.begin():
        b = accept_private_update(
            s,
            token,
            sender_id=destination,
            chat_id=destination,
            chat_type="private",
            sender_is_bot=False,
            now=now,
        )
        return b.id, token


async def packet(setup, index=0, policy=None):
    engine, ids, _, snapshot, default, now = setup
    result = await generate_packet(
        engine, ids[index], snapshot, policy or default, DeterministicCurationProvider(), now=now
    )
    assert result.packet_id
    return result.packet_id


async def test_current_selection_context_partial_missing_and_week_boundary(setup):
    engine, ids, contexts, _, policy, now = setup
    with Session(engine) as s:
        assert (
            read_current_packet(
                s, ids[0], now=now, research_policy=policy.research_policy_version
            ).state
            == "not_generated"
        )
        before = regional_rows(s)
        assert s.scalar(select(func.count()).select_from(CurationJob)) == 0
    pid = await packet(setup)
    with Session(engine) as s, s.begin():
        current = read_current_packet(
            s, ids[0], now=now, research_policy=policy.research_policy_version
        )
        assert current.state == "current" and current.degraded
        assert current.packet.packet_id == pid
        assert current.packet.research_quality == "partial"
        assert (
            read_current_packet(
                s, ids[1], now=now, research_policy=policy.research_policy_version
            ).packet
            is None
        )
        assert (
            read_current_packet(
                s,
                ids[0],
                now=now + timedelta(days=7),
                research_policy=policy.research_policy_version,
            ).packet
            is None
        )
        assert read_current_packet(s, ids[0], now=now, research_policy="other").packet is None
        write_context(
            s,
            ids[0],
            ProductUserContext.model_validate(OUTDOOR),
            expected_revision_id=contexts[0].revision_id,
        )
    with Session(engine) as s:
        older = read_current_packet(
            s, ids[0], now=now, research_policy=policy.research_policy_version
        )
        assert (
            older.state == "older_context"
            and older.context_revision_id != older.packet.context_revision_id
        )
        assert read_packet(s, ids[0], pid)
        assert regional_rows(s) == before
    next_id = await packet(setup)
    with Session(engine) as s:
        assert (
            read_current_packet(
                s, ids[0], now=now, research_policy=policy.research_policy_version
            ).packet.packet_id
            == next_id
        )


@pytest.mark.parametrize("offset,delta", [(0, 0), (1, 0), (2, 0), (3, 7)])
def test_friday_sunday_window(offset, delta):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    friday = datetime(2026, 10, 16, 0, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    assert current_friday(friday + timedelta(days=offset)) == friday.date() + timedelta(days=delta)


async def test_prompt_evolution_preserves_historical_validation(setup, monkeypatch):
    pid = await packet(setup)
    import event_radar.models.packet_validation as validators
    import event_radar.services.packet_generation as generator

    # Simulate a later deployment selecting a new active prompt. Retained v1 remains authoritative.
    monkeypatch.setattr(validators, "PROMPT", "future-reviewed-prompt-v2")
    monkeypatch.setattr(generator, "PROMPT", "future-reviewed-prompt-v2")
    monkeypatch.setattr(
        validators, "validate_result", lambda *args: pytest.fail("current policy used")
    )
    with Session(setup[0]) as s:
        assert read_packet(s, setup[1][0], pid).prompt_hash
    with pytest.raises(ValueError):
        validators.historical_validator("unsupported-v2", "unknown", "0" * 64)


@pytest.mark.parametrize(
    "mode", ["expired", "reused", "spoof", "group", "bot", "unknown", "replaced"]
)
def test_binding_adverse_updates(setup, mode):
    engine, ids, _, _, _, now = setup
    with Session(engine) as s, s.begin():
        token = challenge(s, ids[0], now=now)
    kwargs = dict(sender_id=123, chat_id=123, chat_type="private", sender_is_bot=False, now=now)
    if mode == "expired":
        kwargs["now"] = now + timedelta(minutes=10)
    if mode == "spoof":
        kwargs["sender_id"] = 124
    if mode == "group":
        kwargs["chat_type"] = "group"
    if mode == "bot":
        kwargs["sender_is_bot"] = True
    if mode == "unknown":
        token = "x" * 43
    if mode == "reused":
        with Session(engine) as s, s.begin():
            accept_private_update(s, token, **kwargs)
    if mode == "replaced":
        with Session(engine) as s, s.begin():
            challenge(s, ids[0], now=now)
    with pytest.raises(DeliveryDenied), Session(engine) as s, s.begin():
        accept_private_update(s, token, **kwargs)


def test_binding_hash_revocation_rebind_and_foreign_destination(setup):
    engine, ids, _, _, _, now = setup
    bid, token = bind(engine, ids[0], now)
    with Session(engine) as s, s.begin():
        assert s.scalars(select(DeliveryChallenge)).one().token_hash != token
        with pytest.raises(DeliveryDenied):
            revoke(s, ids[1], bid)
        revoke(s, ids[0], bid)
        revoke(s, ids[0], bid)
    with Session(engine) as s, s.begin():
        token2 = challenge(s, ids[1], now=now)
    with pytest.raises(DeliveryDenied), Session(engine) as s, s.begin():
        accept_private_update(
            s, token2, sender_id=123, chat_id=123, chat_type="private", sender_is_bot=False, now=now
        )
    replacement, _ = bind(engine, ids[0], now, 124)
    with Session(engine) as s:
        assert s.get(DeliveryBinding, replacement).revision == 2
        assert s.get(DeliveryBinding, bid).status == "revoked"


@pytest.mark.parametrize(
    "outcome,expected",
    [
        ("success", "sent"),
        ("rejected", "failed"),
        ("ambiguous", "ambiguous"),
        ("garbage", "ambiguous"),
    ],
)
async def test_delivery_idempotency_outcomes_and_retries(setup, outcome, expected):
    engine, ids, _, _, _, now = setup
    pid = await packet(setup)
    bid, _ = bind(engine, ids[0], now)
    with Session(engine) as s, s.begin():
        before = regional_rows(s)
        job_count = s.scalar(select(func.count()).select_from(CurationJob))
        intent = queue_delivery(s, ids[0], pid, bid, "telegram", development=True)
        assert queue_delivery(s, ids[0], pid, bid, "telegram", development=True) == intent
        with pytest.raises(DeliveryDenied):
            queue_delivery(s, ids[1], pid, bid, "telegram", development=True)
        with pytest.raises(DeliveryDenied):
            queue_delivery(s, ids[0], pid, bid, "telegram")
    transport = FakeTelegramTransport([outcome])
    assert dispatch_fake(engine, intent, transport, development=True) == expected
    again = FakeTelegramTransport()
    assert dispatch_fake(engine, intent, again, development=True) == expected
    assert again.messages == []
    result = dispatch_fake(engine, intent, again, development=True, retry=True)
    assert result == ("sent" if expected == "failed" else expected)
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(DeliveryIntent)) == 1
        assert s.scalar(select(func.count()).select_from(DeliveryAttempt)) == (
            2 if expected == "failed" else 1
        )
        assert regional_rows(s) == before
        assert s.scalar(select(func.count()).select_from(CurationJob)) == job_count
        assert all(len(m.encode("utf-16-le")) // 2 <= 3900 for m in transport.messages)
        rendered = "".join(render_telegram(read_packet(s, ids[0], pid)))
        assert "Community workshop" in rendered and "Attendance availability is unknown" in rendered
        assert "partial" in rendered and "https://" in rendered


async def test_revocation_blocks_queued_delivery_and_changed_revision(setup):
    engine, ids, _, _, _, now = setup
    pid = await packet(setup)
    bid, _ = bind(engine, ids[0], now)
    with Session(engine) as s, s.begin():
        intent = queue_delivery(s, ids[0], pid, bid, "telegram", development=True)
        revoke(s, ids[0], bid)
    fake = FakeTelegramTransport()
    assert dispatch_fake(engine, intent, fake, development=True) == "revoked"
    assert not fake.messages
    with pytest.raises(DeliveryDenied), Session(engine) as s, s.begin():
        queue_delivery(s, ids[0], pid, bid, "telegram", development=True)
    new_binding, _ = bind(engine, ids[0], now)
    with Session(engine) as s, s.begin():
        assert queue_delivery(s, ids[0], pid, new_binding, "telegram", development=True) != intent


async def test_corrupt_current_packet_unavailable(setup):
    pid = await packet(setup)
    engine, ids, _, _, policy, now = setup
    with engine.begin() as c:
        c.execute(text("ALTER TABLE weekend_packets DISABLE TRIGGER USER"))
        c.execute(text("UPDATE weekend_packets SET content_hash=repeat('0',64)"))
        c.execute(text("ALTER TABLE weekend_packets ENABLE TRIGGER USER"))
    with Session(engine) as s:
        assert (
            read_current_packet(
                s, ids[0], now=now, research_policy=policy.research_policy_version
            ).state
            == "unavailable"
        )
        with pytest.raises(PacketCorrupt):
            read_packet(s, ids[0], pid)


def test_authenticated_binding_api_isolation_and_no_store(setup, monkeypatch, caplog):
    engine, ids, _, _, _, now = setup
    bid, token = bind(engine, ids[0], now)
    key, claims, verifier = signing_fixture(monkeypatch)
    monkeypatch.setattr(identity, "auth_config", lambda: CONFIG)
    monkeypatch.setattr(identity, "get_verifier", lambda _: verifier)
    headers = [
        {"Authorization": "Bearer " + signed(key, {**claims, "sub": str(uid)})} for uid in ids
    ]
    with TestClient(create_app()) as client:
        url = "/api/me/delivery/bindings"
        response = client.get(url, headers=headers[0])
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        assert "destination" not in response.text and token not in response.text
        assert client.get(url, headers=headers[1]).json() == []
        assert client.post(f"{url}/{bid}/revoke", headers=headers[1]).status_code == 404
        assert client.post("/api/me/delivery/telegram/challenge").status_code == 404
        assert client.get("/api/me/packets/current").status_code == 401
        assert client.get("/api/me/packets/current", headers=headers[1]).status_code == 200
        issued = client.post("/api/me/delivery/telegram/challenge", headers=headers[1])
        assert issued.status_code == 404
        assert client.get("/api/me/delivery/telegram/config", headers=headers[1]).status_code == 404
        assert client.post(f"{url}/{bid}/revoke", headers=headers[0]).status_code == 204
    assert token not in caplog.text


def test_delivery_rls_denies_client(setup):
    engine = setup[0]
    role = "delivery_reader_" + uuid4().hex
    with engine.begin() as c:
        c.execute(text(f"CREATE ROLE {role}"))
        c.execute(
            text(
                "GRANT SELECT ON delivery_bindings, delivery_challenges, "
                f"delivery_intents, delivery_attempts TO {role}"
            )
        )
    try:
        with engine.begin() as c:
            c.execute(text(f"SET LOCAL ROLE {role}"))
            for table in (
                "delivery_bindings",
                "delivery_challenges",
                "delivery_intents",
                "delivery_attempts",
            ):
                assert c.execute(text(f"SELECT * FROM {table}")).all() == []
    finally:
        with engine.begin() as c:
            c.execute(text(f"DROP OWNED BY {role}"))
            c.execute(text(f"DROP ROLE {role}"))


async def test_concurrent_delivery_intents_and_single_use_challenge(setup):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    engine, ids, _, _, _, now = setup
    pid = await packet(setup)
    with Session(engine) as s, s.begin():
        token = challenge(s, ids[0], now=now)
    barrier = Barrier(2)

    def consume(_):
        barrier.wait(timeout=5)
        try:
            with Session(engine) as s, s.begin():
                return accept_private_update(
                    s,
                    token,
                    sender_id=123,
                    chat_id=123,
                    chat_type="private",
                    sender_is_bot=False,
                    now=now,
                ).id
        except DeliveryDenied:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(consume, range(2)))
    assert sum(result is not None for result in results) == 1
    bid = next(result for result in results if result)
    barrier = Barrier(2)

    def queue(_):
        barrier.wait(timeout=5)
        with Session(engine) as s, s.begin():
            return queue_delivery(s, ids[0], pid, bid, "telegram", development=True)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(queue, range(2)))
    assert results[0] == results[1]
    fake = FakeTelegramTransport()
    barrier = Barrier(2)

    def send(_):
        barrier.wait(timeout=5)
        return dispatch_fake(engine, results[0], fake, development=True)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(send, range(2)))
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(DeliveryAttempt)) == 1


async def test_failed_retry_limit_and_interrupted_claim(setup):
    engine, ids, _, _, _, now = setup
    pid = await packet(setup)
    bid, _ = bind(engine, ids[0], now)
    with Session(engine) as s, s.begin():
        intent = queue_delivery(s, ids[0], pid, bid, "telegram", development=True)
    fake = FakeTelegramTransport(["rejected"] * 4)
    for _ in range(4):
        assert dispatch_fake(engine, intent, fake, development=True, retry=True) == "failed"
    assert len(fake.messages) == 3
    with Session(engine) as s:
        assert s.get(DeliveryIntent, intent).attempts == 3
    newer, _ = bind(engine, ids[0], now, 124)
    with Session(engine) as s, s.begin():
        interrupted = queue_delivery(s, ids[0], pid, newer, "telegram", development=True)
        s.get(DeliveryIntent, interrupted).status = "sending"
    fake = FakeTelegramTransport()
    assert dispatch_fake(engine, interrupted, fake, development=True, retry=True) == "sending"
    assert not fake.messages


async def test_multimessage_ambiguous_and_unicode_rendering(setup, monkeypatch):
    engine, ids, _, _, _, now = setup
    pid = await packet(setup)
    bid, _ = bind(engine, ids[0], now)
    with Session(engine) as s, s.begin():
        intent = queue_delivery(s, ids[0], pid, bid, "telegram", development=True)
        original = read_packet(s, ids[0], pid)
        first = original.recommendations[0]
        unusual = original.model_copy(
            update={
                "recommendations": (
                    first.model_copy(
                        update={"facts": first.facts.model_copy(update={"title": "😀" * 5000})}
                    ),
                )
            }
        )
        chunks = render_telegram(unusual)
        assert len(chunks) > 2 and "😀" * 5000 in "".join(chunks)
        assert all(len(c.encode("utf-16-le")) // 2 <= 3900 for c in chunks)
    import event_radar.services.packet_delivery as delivery

    monkeypatch.setattr(delivery, "render_telegram", lambda _: ["first", "second"])
    fake = FakeTelegramTransport(["success", "rejected"])
    assert dispatch_fake(engine, intent, fake, development=True) == "ambiguous"
    assert dispatch_fake(engine, intent, fake, development=True, retry=True) == "ambiguous"
    assert fake.messages == ["first", "second"]


async def test_current_precedence_and_authenticated_two_user_api(setup, monkeypatch):

    import event_radar.api.packets as api

    engine, ids, _, _, policy, now = setup
    first = await packet(setup)
    second = await packet(
        setup, policy=policy.model_copy(update={"configuration_version": "reviewed-second"})
    )
    other = await packet(setup, 1)
    with Session(engine) as s:
        current = read_current_packet(
            s, ids[0], now=now, research_policy=policy.research_policy_version
        )
        assert current.packet.packet_id == second != first
        stale = read_current_packet(
            s, ids[0], now=now + timedelta(hours=98), research_policy=policy.research_policy_version
        )
        # The fixture's next-week read must never return the previous weekend.
        assert stale.packet is None
    monkeypatch.setattr(
        api,
        "read_current_packet",
        lambda s, uid, **kwargs: read_current_packet(
            s, uid, now=now, research_policy=policy.research_policy_version
        ),
    )
    key, claims, verifier = signing_fixture(monkeypatch)
    monkeypatch.setattr(identity, "auth_config", lambda: CONFIG)
    monkeypatch.setattr(identity, "get_verifier", lambda _: verifier)
    with TestClient(create_app()) as client:
        for uid, expected in zip(ids, (second, other), strict=True):
            headers = {"Authorization": "Bearer " + signed(key, {**claims, "sub": str(uid)})}
            response = client.get(f"/api/me/packets/current?user_id={ids[1]}", headers=headers)
            assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
            assert response.json()["packet"]["packet_id"] == str(expected)


async def test_current_quality_precedence_superseded_snapshot_and_staleness(setup):
    from event_radar.db.regional import begin_regional_research_run, complete_regional_research_run
    from event_radar.models.regional import RegionalWeekendUniverse
    from tests.test_weekend_packets import universe

    engine, ids, _, snapshot_id, policy, now = setup
    # Use the same research identity and factual options with a later fully successful snapshot.
    data = universe().model_dump(mode="json")
    data["scope"]["as_of"] = (now + timedelta(hours=1)).isoformat()
    data["sources"] = [r for r in data["sources"] if r["status"] != "failed"]
    for source in data["sources"]:
        source["status"], source["failure_code"] = "success", None
    data["diagnostics"], data["unknowns"] = [], []
    research = RegionalWeekendUniverse.model_validate(data)
    with Session(engine) as s, s.begin():
        run = begin_regional_research_run(s, research.scope)
        snap = complete_regional_research_run(s, run.id, research, quality_status="success")
        sid = snap.id
    full = await generate_packet(
        engine, ids[0], sid, policy, DeterministicCurationProvider(), now=now + timedelta(hours=2)
    )
    # A later generation on older partial research must not displace full quality.
    partial_id = await packet(setup)
    with Session(engine) as s:
        selected = read_current_packet(
            s, ids[0], now=now + timedelta(hours=2), research_policy=policy.research_policy_version
        )
        assert selected.packet.packet_id == full.packet_id != partial_id
        assert not selected.degraded
    # Account B only has the old pinned snapshot; it stays visible with explicit supersession.
    await packet(setup, 1)
    with Session(engine) as s:
        selected = read_current_packet(
            s, ids[1], now=now + timedelta(hours=2), research_policy=policy.research_policy_version
        )
        assert selected.snapshot_superseded and selected.degraded
        assert selected.packet.snapshot_id == snapshot_id
    short_policy = policy.model_copy(update={"max_research_age_hours": 1})
    result = await generate_packet(
        engine,
        ids[0],
        sid,
        short_policy,
        DeterministicCurationProvider(),
        now=now + timedelta(hours=1),
    )
    with Session(engine) as s:
        selected = read_current_packet(
            s, ids[0], now=now + timedelta(hours=3), research_policy=policy.research_policy_version
        )
        assert selected.packet.packet_id == result.packet_id
        assert selected.research_stale and selected.degraded


async def test_delivery_database_audit_and_foreign_packet_constraint(setup):
    from sqlalchemy.exc import IntegrityError

    engine, ids, _, _, _, now = setup
    pid = await packet(setup)
    bid, _ = bind(engine, ids[1], now)
    # Even a backend insertion cannot associate A's packet with B's binding.
    with pytest.raises(IntegrityError), Session(engine) as s, s.begin():
        s.add(
            DeliveryIntent(
                id=uuid4(),
                user_id=ids[1],
                packet_id=pid,
                binding_id=bid,
                channel="telegram",
                status="pending",
                attempts=0,
                created_at=now,
                updated_at=now,
            )
        )
    for statement in (
        "DELETE FROM delivery_bindings",
        "UPDATE delivery_bindings SET destination='456'",
        "UPDATE delivery_challenges SET consumed_at=NULL",
    ):
        with pytest.raises(IntegrityError), engine.begin() as c:
            c.execute(text(statement))
