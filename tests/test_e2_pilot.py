"""Integrated ordinary-user proof; optional local E2 DB uses no destructive fixture resets."""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from alembic import command
from event_radar.api.app import create_app
from event_radar.auth import identity
from event_radar.auth.identity import AuthenticatedUser
from event_radar.db.curation_preflight import curation_preflight
from event_radar.db.delivery import queue_delivery
from event_radar.db.evidence import integrity_envelope
from event_radar.db.models import CurationJob, DeliveryBinding
from event_radar.db.packets import read_packet
from event_radar.db.snapshot_import import import_public_snapshot
from event_radar.models.delivery_authority import PilotDeliveryAuthority
from event_radar.models.weekend_packet import CurationPolicy, digest
from event_radar.services.packet_delivery import dispatch_delivery
from event_radar.services.packet_generation import generate_packet
from event_radar.services.personalized_curation import DeterministicCurationProvider
from event_radar.services.telegram_transport import TelegramHTTPResponse, TelegramHTTPTransport
from tests.auth_helpers import CONFIG, signed, signing_fixture
from tests.test_development_evidence import regional_rows
from tests.test_weekend_packets import no_external_calls, universe
from tests.test_weekend_packets_integration import setup

__all__ = ["no_external_calls", "setup"]


@pytest.fixture(autouse=True)
def forbid_unintended_network(monkeypatch):
    import socket

    def denied(*args, **kwargs):
        raise AssertionError("External Python network is forbidden in pilot proof")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)


@pytest.fixture
def pilot_db(request, monkeypatch):
    if os.environ.get("E2_PILOT_LOCAL") == "1":
        from event_radar.pilot import LOCAL_URL, local_engine

        engine = local_engine()
        monkeypatch.setenv("DATABASE_URL", LOCAL_URL)
        yield engine
        engine.dispose()
    else:
        engine, config = request.getfixturevalue("database")
        command.upgrade(config, "head")
        yield engine


def exported():
    path = os.environ.get("E2_PILOT_EXPORT")
    if path:
        value = json.loads(Path(path).read_text())
        assert value["sha256"] == os.environ["E2_PILOT_EXPORT_SHA256"]
        return value
    research = universe()
    return integrity_envelope(
        {
            "availability": "exported",
            "snapshot_id": str(uuid4()),
            "universe_id": str(uuid4()),
            "snapshot_content_hash": digest(research.model_dump(mode="json")),
            "quality_status": "partial",
            "universe": research.model_dump(mode="json"),
            "discovery_summary": None,
        }
    )


async def test_connected_ordinary_user_pilot(pilot_db, monkeypatch, caplog):
    engine = pilot_db
    from event_radar.shared import worker

    def no_research(*args, **kwargs):
        raise AssertionError("Pilot must not regenerate upstream research")

    monkeypatch.setattr(worker, "run_regional_worker", no_research)
    envelope = exported()
    with Session(engine) as s, s.begin():
        sid = import_public_snapshot(s, envelope)
        assert import_public_snapshot(s, envelope) == sid
    source = envelope["payload"]["universe"]
    scope = source["scope"]
    # Synthetic clock only for the committed fixture. Real export assessment uses actual UTC time.
    now = (
        datetime.now(UTC)
        if os.environ.get("E2_PILOT_EXPORT")
        else datetime.fromisoformat(scope["as_of"]) + timedelta(hours=1)
    )
    key, claims, verifier = signing_fixture(monkeypatch)
    monkeypatch.setattr(identity, "auth_config", lambda: CONFIG)
    monkeypatch.setattr(identity, "get_verifier", lambda _: verifier)
    import event_radar.api.packets as packets_api
    from event_radar.db.current_packet import read_current_packet

    monkeypatch.setattr(
        packets_api,
        "read_current_packet",
        lambda s, uid, **kwargs: read_current_packet(
            s, uid, now=now, research_policy=scope["research_policy_version"]
        ),
    )
    ids = [uuid4(), uuid4()]
    headers = [
        {"Authorization": "Bearer " + signed(key, {**claims, "sub": str(uid)})} for uid in ids
    ]
    secret = "synthetic_webhook_auth_" + uuid4().hex
    app = create_app(telegram_webhook_secret=secret)
    with TestClient(app) as client:
        profile = {
            "base_location": {
                "locality": "Synthetic pilot town",
                "timezone": "America/Los_Angeles",
            },
            "interests": [source["opportunities"][0]["title"][:400]],
        }
        context = client.post("/api/me/context", headers=headers[0], json=profile)
        assert context.status_code == 201
        changed = client.put(
            "/api/me/context",
            headers=headers[0],
            json={
                "expected_revision_id": context.json()["revision_id"],
                "context": {**profile, "objectives": ["Explore an interesting local activity"]},
            },
        )
        assert changed.status_code == 200
        assert (
            client.put(
                "/api/me/context",
                headers=headers[0],
                json={"expected_revision_id": context.json()["revision_id"], "context": profile},
            ).status_code
            == 409
        )
        assert client.get("/api/me/context", headers=headers[1]).status_code == 404
        with Session(engine) as s:
            before = regional_rows(s)
            policy = CurationPolicy(research_policy_version=scope["research_policy_version"])
            preflight = curation_preflight(s, AuthenticatedUser(id=ids[0]), sid, policy, now=now)
            assert preflight.ready, preflight.blockers
        result = await generate_packet(
            engine,
            ids[0],
            sid,
            policy,
            DeterministicCurationProvider(),
            now=now,
            expected_context_revision_id=preflight.context_revision_id,
        )
        assert result.packet_id, result.failure_code
        current = client.get("/api/me/packets/current", headers=headers[0])
        assert current.status_code == 200 and current.json()["packet"]["packet_id"] == str(
            result.packet_id
        )
        url = f"/api/me/packets/{result.packet_id}"
        assert client.get(url, headers=headers[0]).status_code == 200
        assert client.get(url, headers=headers[1]).status_code == 404
        assert client.get("/api/me/packets/current", headers=headers[1]).json()["packet"] is None
        challenge = client.post("/api/me/delivery/telegram/challenge", headers=headers[0]).json()[
            "challenge"
        ]
        destination = int(uuid4().int % (2**40)) + 1
        update = {
            "update_id": 1,
            "message": {
                "text": "/start " + challenge,
                "date": int(datetime.now(UTC).timestamp()),
                "from": {"id": destination, "is_bot": False},
                "chat": {"id": destination, "type": "private"},
            },
        }
        inbound = "/api/integrations/telegram/webhook"
        assert client.post(inbound, json=update).status_code == 403
        assert client.post(
            inbound, json=update, headers={"X-Telegram-Bot-Api-Secret-Token": secret}
        ).json() == {"accepted": True}
        assert client.post(
            inbound, json=update, headers={"X-Telegram-Bot-Api-Secret-Token": secret}
        ).json() == {"accepted": False}
        binding = client.get("/api/me/delivery/bindings", headers=headers[0]).json()[0]
        assert client.get("/api/me/delivery/bindings", headers=headers[1]).json() == []
        from uuid import UUID

        bid = UUID(binding["id"])
        authority = PilotDeliveryAuthority(
            approval_reference="synthetic-offline-proof",
            user_id=ids[0],
            packet_id=result.packet_id,
            binding_id=bid,
            issued_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        with Session(engine) as s, s.begin():
            intent = queue_delivery(
                s, ids[0], result.packet_id, bid, "telegram", approval=authority
            )
        calls = []

        def post(url, body, timeout):
            assert engine.pool.checkedout() == 0, "Network must not hold a DB transaction"
            calls.append(body["text"])
            return TelegramHTTPResponse(
                200,
                json.dumps(
                    {"ok": True, "result": {"message_id": len(calls), "chat": {"id": destination}}}
                ).encode(),
            )

        transport = TelegramHTTPTransport(token="synthetic-token", authorized=True, post=post)
        assert dispatch_delivery(engine, intent, transport, approval=authority) == "sent"
        count = len(calls)
        assert dispatch_delivery(engine, intent, transport, approval=authority) == "sent"
        assert len(calls) == count > 0
        assert (
            client.post(f"/api/me/delivery/bindings/{bid}/revoke", headers=headers[0]).status_code
            == 204
        )
    with Session(engine) as s:
        assert regional_rows(s) == before
        packet = read_packet(s, ids[0], result.packet_id)
        assert packet.snapshot_hash == envelope["payload"]["snapshot_content_hash"]
        assert packet.policy.research_policy_version == scope["research_policy_version"]
        assert s.get(DeliveryBinding, bid).status == "revoked"
        assert len(s.scalars(select(CurationJob).where(CurationJob.user_id == ids[0])).all()) == 1
    assert (
        challenge not in caplog.text
        and secret not in caplog.text
        and "synthetic-token" not in caplog.text
    )
    print(
        json.dumps(
            {
                "snapshot_id": str(sid),
                "packet_id": str(result.packet_id),
                "request_bytes": preflight.request_bytes,
                "opportunities": preflight.opportunities,
                "recommendations": len(packet.recommendations),
                "fake_messages": count,
                "real_provider_calls": 0,
            }
        )
    )


def test_import_rejects_corruption(pilot_db):
    envelope = exported()
    envelope["sha256"] = "0" * 64
    with pytest.raises(ValueError), Session(pilot_db) as s, s.begin():
        import_public_snapshot(s, envelope)


@pytest.mark.parametrize(
    "kind", ["timeout", "rejected", "bad_json", "server", "wrong_chat", "oversized", "success"]
)
def test_mocked_telegram_http(kind, caplog):
    calls = []

    def post(url, body, timeout):
        calls.append(body)
        if kind == "timeout":
            raise TimeoutError("SENSITIVE_TOKEN")
        if kind == "bad_json":
            return TelegramHTTPResponse(200, b"not json")
        if kind == "oversized":
            return TelegramHTTPResponse(200, b"x" * 20000)
        if kind == "rejected":
            return TelegramHTTPResponse(403, b'{"ok":false,"error_code":403}')
        if kind == "server":
            return TelegramHTTPResponse(500, b'{"ok":false,"error_code":500}')
        return TelegramHTTPResponse(
            200,
            json.dumps(
                {
                    "ok": True,
                    "result": {
                        "message_id": 1,
                        "chat": {"id": 999 if kind == "wrong_chat" else 123},
                    },
                }
            ).encode(),
        )

    inert = TelegramHTTPTransport(token="SENSITIVE_TOKEN", post=post)
    assert inert.send("123", "private message") == "rejected" and not calls
    transport = TelegramHTTPTransport(token="SENSITIVE_TOKEN", authorized=True, post=post)
    expected = "success" if kind == "success" else "rejected" if kind == "rejected" else "ambiguous"
    assert transport.send("123", "private message") == expected and len(calls) == 1
    assert "SENSITIVE_TOKEN" not in caplog.text and "private message" not in caplog.text


def test_pilot_policy_explicit_configuration(monkeypatch):
    from event_radar.api.config import packet_research_policy

    monkeypatch.delenv("PACKET_RESEARCH_POLICY", raising=False)
    assert packet_research_policy() == "e1-weekly-sonoma-v1"
    monkeypatch.setenv("PACKET_RESEARCH_POLICY", "e1-wp7-liveproof-2026-10-16-v1")
    assert packet_research_policy() == "e1-wp7-liveproof-2026-10-16-v1"
    monkeypatch.setenv("PACKET_RESEARCH_POLICY", "arbitrary")
    with pytest.raises(ValueError):
        packet_research_policy()


def test_webhook_inert_and_authentication_first():
    with TestClient(create_app()) as client:
        assert client.post("/api/integrations/telegram/webhook", json={}).status_code == 404
    with TestClient(create_app(telegram_webhook_secret="s" * 40)) as client:
        assert client.post("/api/integrations/telegram/webhook", json={}).status_code == 403
        assert (
            client.post(
                "/api/integrations/telegram/webhook",
                content=b"x" * 16385,
                headers={"X-Telegram-Bot-Api-Secret-Token": "s" * 40},
            ).status_code
            == 413
        )


@pytest.mark.parametrize(
    "mode,blocker",
    [
        ("stale", "research_stale"),
        ("future", "research_future"),
        ("expired", "weekend_expired"),
        ("wrong_policy", "research_policy_mismatch"),
        ("size", "request_size_limit"),
        ("count", "opportunity_limit"),
        ("credentials", "credentials_not_supplied"),
        ("pricing", "model_pricing_review_required"),
        ("exposure", "estimated_exposure_exceeds_review"),
    ],
)
def test_preflight_blocks_unready_inputs(setup, mode, blocker):
    from event_radar.db.curation_preflight import PricingReview

    engine, ids, _, sid, policy, now = setup
    pricing = None
    credentials = True
    if mode == "stale":
        now += timedelta(days=5)
    if mode == "future":
        now -= timedelta(days=1)
    if mode == "expired":
        now += timedelta(days=10)
    if mode == "wrong_policy":
        policy = policy.model_copy(update={"research_policy_version": "other-v1"})
    if mode == "size":
        policy = policy.model_copy(update={"max_input_bytes": 1000})
    if mode == "count":
        policy = policy.model_copy(update={"max_opportunities": 1})
    if mode in ("credentials", "pricing", "exposure"):
        policy = policy.model_copy(
            update={"provider": "openai", "model": "synthetic-reviewed-model"}
        )
        pricing = PricingReview(
            model=policy.model,
            input_usd_per_million=4,
            model_context_tokens=1000000,
            structured_output_supported=True,
            output_usd_per_million=20,
            reviewed_at=now,
            reference="synthetic-only",
            exposure_envelope_usd=0.001 if mode == "exposure" else 2,
        )
        if mode == "credentials":
            credentials = False
        if mode == "pricing":
            pricing = None
    with Session(engine) as s:
        result = curation_preflight(
            s,
            AuthenticatedUser(id=ids[0]),
            sid,
            policy,
            pricing=pricing,
            credentials_ready=credentials,
            now=now,
        )
        assert not result.ready and blocker in result.blockers
        assert s.scalars(select(CurationJob)).all() == []


async def test_preflight_pins_context_and_claim_replay(setup):
    from event_radar.db.curation_preflight import PricingReview

    engine, ids, contexts, sid, policy, now = setup
    live_policy = policy.model_copy(
        update={"provider": "openai", "model": "synthetic-reviewed-model"}
    )
    review = PricingReview(
        model=live_policy.model,
        input_usd_per_million=4,
        model_context_tokens=1000000,
        structured_output_supported=True,
        output_usd_per_million=20,
        reviewed_at=now,
        reference="synthetic-only",
        exposure_envelope_usd=2,
    )
    with Session(engine) as s:
        ready = curation_preflight(
            s,
            AuthenticatedUser(id=ids[0]),
            sid,
            live_policy,
            pricing=review,
            credentials_ready=True,
            now=now,
        )
        assert ready.ready and 0 < ready.estimated_exposure_usd < 2
        assert ready.context_revision_id == contexts[0].revision_id
    blocked = await generate_packet(
        engine,
        ids[0],
        sid,
        policy,
        DeterministicCurationProvider(),
        now=now,
        expected_context_revision_id=uuid4(),
    )
    assert blocked.failure_code == "context_changed"
    generated = await generate_packet(
        engine,
        ids[0],
        sid,
        policy,
        DeterministicCurationProvider(),
        now=now,
        expected_context_revision_id=contexts[0].revision_id,
    )
    with Session(engine) as s:
        replay = curation_preflight(s, AuthenticatedUser(id=ids[0]), sid, policy, now=now)
        assert replay.existing_packet_id == generated.packet_id


async def test_live_dispatch_revocation_between_chunks_and_approval_scope(setup, monkeypatch):
    import event_radar.services.packet_delivery as dispatcher
    from event_radar.db.delivery import DeliveryDenied, revoke
    from tests.test_packet_delivery_integration import bind, packet

    engine, ids, _, _, _, now = setup
    pid = await packet(setup)
    bid, _ = bind(engine, ids[0], now)
    approval = PilotDeliveryAuthority(
        approval_reference="synthetic-only",
        user_id=ids[0],
        packet_id=pid,
        binding_id=bid,
        issued_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    with Session(engine) as s, s.begin():
        intent = queue_delivery(s, ids[0], pid, bid, "telegram", approval=approval)
    monkeypatch.setattr(dispatcher, "render_telegram", lambda _: ["one", "two"])
    calls = []

    def post(url, body, timeout):
        assert engine.pool.checkedout() == 0
        calls.append(body)
        with Session(engine) as s, s.begin():
            revoke(s, ids[0], bid)
        return TelegramHTTPResponse(200, b'{"ok":true,"result":{"message_id":1,"chat":{"id":123}}}')

    transport = TelegramHTTPTransport(token="synthetic", authorized=True, post=post)
    with pytest.raises(DeliveryDenied):
        dispatch_delivery(engine, intent, transport)
    wrong = approval.model_copy(update={"user_id": ids[1]})
    with pytest.raises(DeliveryDenied):
        dispatch_delivery(engine, intent, transport, approval=wrong)
    assert dispatch_delivery(engine, intent, transport, approval=approval) == "ambiguous"
    assert len(calls) == 1
    assert (
        dispatch_delivery(engine, intent, transport, approval=approval, retry=True) == "ambiguous"
    )
    assert len(calls) == 1
