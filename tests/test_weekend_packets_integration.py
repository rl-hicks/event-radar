"""Durable two-user packet evidence, only on the guarded disposable PostgreSQL."""

import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from event_radar.api.app import create_app
from event_radar.auth import identity
from event_radar.db.contexts import write_context
from event_radar.db.models import (
    CurationJob,
    UserContextRevision,
    WeekendPacketRecord,
)
from event_radar.db.packets import PacketCorrupt, read_packet
from event_radar.db.regional import begin_regional_research_run, complete_regional_research_run
from event_radar.models.product_context import ProductUserContext
from event_radar.models.weekend_packet import CurationPolicy, CurationResult, CurationUsage
from event_radar.services.packet_generation import generate_packet
from event_radar.services.personalized_curation import (
    DeterministicCurationProvider,
    ProviderResponse,
)
from tests.auth_helpers import CONFIG, signed, signing_fixture
from tests.test_development_evidence import regional_rows
from tests.test_weekend_packets import OUTDOOR, SOCIAL, no_external_calls, universe

# Imported autouse fixture ensures every test in this module blocks external HTTP.
__all__ = ["no_external_calls"]


@pytest.fixture
def setup(database):
    engine, config = database
    command.upgrade(config, "head")
    research = universe()
    ids = (uuid4(), uuid4())
    with Session(engine) as session, session.begin():
        run = begin_regional_research_run(session, research.scope)
        snapshot = complete_regional_research_run(
            session, run.id, research, quality_status="partial", failure_code="timeout"
        )
        snapshot_id = snapshot.id
        contexts = tuple(
            write_context(
                session, uid, ProductUserContext.model_validate(profile), expected_revision_id=None
            )
            for uid, profile in zip(ids, (SOCIAL, OUTDOOR), strict=True)
        )
    return (
        engine,
        ids,
        contexts,
        snapshot_id,
        CurationPolicy(research_policy_version=research.scope.research_policy_version),
        research.scope.as_of + timedelta(hours=1),
    )


async def test_two_authenticated_users_one_snapshot(setup, monkeypatch, caplog):
    engine, ids, contexts, snapshot, policy, now = setup
    from event_radar.shared import collection, discovery, semantic_analysis, worker

    def forbidden(*args, **kwargs):
        raise AssertionError("Shared research must not run")

    monkeypatch.setattr(worker, "run_regional_worker", forbidden)
    # Any newly introduced research call is also detectable through module entry points.
    for module in (collection, semantic_analysis, discovery):
        for name in dir(module):
            if name.startswith(("run_", "collect_", "analyze_", "discover_")) and callable(
                getattr(module, name)
            ):
                monkeypatch.setattr(module, name, forbidden)
    with Session(engine) as session:
        before = regional_rows(session)
    results = [
        await generate_packet(
            engine, uid, snapshot, policy, DeterministicCurationProvider(), now=now
        )
        for uid in ids
    ]
    assert all(result.status == "partial" for result in results)
    key, claims, verifier = signing_fixture(monkeypatch)
    monkeypatch.setattr(identity, "auth_config", lambda: CONFIG)
    monkeypatch.setattr(identity, "get_verifier", lambda _: verifier)
    headers = [
        {"Authorization": "Bearer " + signed(key, {**claims, "sub": str(uid)})} for uid in ids
    ]
    with TestClient(create_app()) as client:
        packets = []
        for index, result in enumerate(results):
            url = f"/api/me/packets/{result.packet_id}"
            response = client.get(url, headers=headers[index])
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
            packet = response.json()
            packets.append(packet)
            assert packet["context_revision_id"] == str(contexts[index].revision_id)
            assert packet["context_hash"] == contexts[index].content_hash
            assert client.get(url, headers=headers[1 - index]).status_code == 404
            assert client.get(url).status_code == 401
            assert client.post(url, headers=headers[index]).status_code == 405
            assert client.get(url, headers=headers[index]).json() == packet
        spoof = client.get(
            f"/api/me/packets/{results[0].packet_id}?user_id={ids[0]}",
            headers={**headers[1], "X-User-ID": str(ids[0])},
        )
        assert spoof.status_code == 404 and spoof.headers["cache-control"] == "no-store"
        assert client.get(f"/api/users/{ids[0]}/packets", headers=headers[1]).status_code == 404
        assert client.get("/api/me/packets/not-a-uuid", headers=headers[0]).status_code == 422
        bad = signed(key, {**claims, "role": "service_role"})
        assert (
            client.get(
                f"/api/me/packets/{results[0].packet_id}",
                headers={"Authorization": "Bearer " + bad},
            ).status_code
            == 401
        )
    assert packets[0]["snapshot_id"] == packets[1]["snapshot_id"] == str(snapshot)
    assert packets[0]["snapshot_hash"] == packets[1]["snapshot_hash"]
    assert packets[0]["recommendations"][0]["facts"]["opportunity_id"] == "community-workshop"
    assert packets[1]["recommendations"][0]["facts"]["opportunity_id"] == "synthetic-ridge-route"
    assert (
        packets[0]["recommendations"][0]["rationale"]
        != packets[1]["recommendations"][0]["rationale"]
    )
    with Session(engine) as session:
        assert regional_rows(session) == before
        assert "Community workshop" not in str(before)
        assert session.scalar(select(func.count()).select_from(WeekendPacketRecord)) == 2
        for uid, result in zip(ids, results, strict=True):
            assert read_packet(session, uid, result.packet_id)
    logs = "\n".join(r.getMessage() for r in caplog.records)
    assert "Conversation through" not in logs and "Long ridge route" not in logs


async def test_concurrent_requests_one_call_and_replay(setup):
    engine, ids, contexts, snapshot, policy, now = setup
    entered, release = asyncio.Event(), asyncio.Event()

    class Slow(DeterministicCurationProvider):
        calls = 0

        async def curate(self, request):
            self.calls += 1
            entered.set()
            await release.wait()
            return await super().curate(request)

    provider = Slow()
    first = asyncio.create_task(
        generate_packet(engine, ids[0], snapshot, policy, provider, now=now)
    )
    await entered.wait()
    second = await generate_packet(engine, ids[0], snapshot, policy, provider, now=now)
    assert second.status == "running"
    release.set()
    completed = await first
    replay = await generate_packet(engine, ids[0], snapshot, policy, provider, now=now)
    assert replay == completed and provider.calls == 1
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(CurationJob)) == 1
        assert session.scalar(select(func.count()).select_from(WeekendPacketRecord)) == 1


async def test_context_changes_during_curation_and_new_revision(setup):
    engine, ids, contexts, snapshot, policy, now = setup

    class Change(DeterministicCurationProvider):
        async def curate(self, request):
            with Session(engine) as session, session.begin():
                write_context(
                    session,
                    ids[0],
                    ProductUserContext.model_validate(OUTDOOR),
                    expected_revision_id=contexts[0].revision_id,
                )
            return await super().curate(request)

    failed = await generate_packet(engine, ids[0], snapshot, policy, Change(), now=now)
    assert failed.failure_code == "context_changed"
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(WeekendPacketRecord)) == 0
    valid = await generate_packet(
        engine, ids[0], snapshot, policy, DeterministicCurationProvider(), now=now
    )
    with Session(engine) as session:
        packet = read_packet(session, ids[0], valid.packet_id)
        assert packet.context_revision_id != contexts[0].revision_id
        assert packet.recommendations[0].facts.opportunity_id == "synthetic-ridge-route"


@pytest.mark.parametrize("mode", ["timeout", "extra", "opportunity", "evidence", "exception"])
async def test_failed_refresh_preserves_packet_and_never_retries(setup, mode):
    engine, ids, contexts, snapshot, policy, now = setup
    good = await generate_packet(
        engine, ids[0], snapshot, policy, DeterministicCurationProvider(), now=now
    )
    refresh = policy.model_copy(
        update={"configuration_version": "reviewed-v2", "timeout_seconds": 0.01}
    )

    class Bad(DeterministicCurationProvider):
        calls = 0

        async def curate(self, request):
            self.calls += 1
            if mode == "timeout":
                await asyncio.sleep(1)
            if mode == "exception":
                raise RuntimeError("PRIVATE_PROVIDER_CONTENT")
            response = await super().curate(request)
            payload = response.result.model_dump(mode="json")
            if mode == "extra":
                payload["private_prompt"] = "PRIVATE_PROVIDER_CONTENT"
            if mode == "opportunity":
                payload["recommendations"][0]["opportunity_id"] = "not-real"
            if mode == "evidence":
                payload["recommendations"][0]["evidence_ids"] = ["park"]
            return ProviderResponse(CurationResult.model_validate(payload), CurationUsage())

    provider = Bad()
    failed = await generate_packet(engine, ids[0], snapshot, refresh, provider, now=now)
    assert failed.status == "failed"
    assert failed.failure_code == ("timeout" if mode == "timeout" else "invalid_response")
    assert await generate_packet(engine, ids[0], snapshot, refresh, provider, now=now) == failed
    assert provider.calls == 1
    with Session(engine) as session:
        assert read_packet(session, ids[0], good.packet_id)
        assert session.scalar(select(func.count()).select_from(WeekendPacketRecord)) == 1
        jobs = session.scalars(select(CurationJob)).all()
        assert "PRIVATE_PROVIDER_CONTENT" not in str([j.usage_payload for j in jobs])


@pytest.mark.parametrize(
    "mode,code",
    [
        ("missing_snapshot", "snapshot_missing"),
        ("missing_context", "context_missing"),
        ("stale", "research_stale"),
        ("incompatible", "invalid_input"),
        ("snapshot_corrupt", "invalid_input"),
        ("context_corrupt", "context_corrupt"),
        ("expired", "weekend_expired"),
    ],
)
async def test_unavailable_inputs_no_calls(setup, mode, code):
    engine, ids, contexts, snapshot, policy, now = setup
    uid = ids[0]
    if mode == "missing_snapshot":
        snapshot = uuid4()
    if mode == "missing_context":
        uid = uuid4()
    if mode == "stale":
        now += timedelta(days=6)
    if mode == "expired":
        now = universe().scope.window.end
    if mode == "incompatible":
        policy = policy.model_copy(update={"research_policy_version": "other-v1"})
    if mode == "snapshot_corrupt":
        # Privileged synthetic corruption: actual E1 snapshot trigger must be disabled explicitly.
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE regional_universe_snapshots DISABLE TRIGGER USER"))
            connection.execute(
                text("UPDATE regional_universe_snapshots SET content_hash = repeat('0',64)")
            )
            connection.execute(text("ALTER TABLE regional_universe_snapshots ENABLE TRIGGER USER"))
    if mode == "context_corrupt":
        with Session(engine) as session, session.begin():
            session.add(
                UserContextRevision(
                    id=uuid4(),
                    user_id=uid,
                    revision=2,
                    schema_version="user-context-v1",
                    content_hash="0" * 64,
                    context_payload=SOCIAL,
                )
            )

    class Never:
        async def curate(self, request):
            pytest.fail("provider must not be called")

    result = await generate_packet(engine, uid, snapshot, policy, Never(), now=now)
    assert result.failure_code == code
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(CurationJob)) == 0


async def test_packet_database_immutability_rls_and_integrity(setup):
    engine, ids, contexts, snapshot, policy, now = setup
    result = await generate_packet(
        engine, ids[0], snapshot, policy, DeterministicCurationProvider(), now=now
    )
    for sql in (
        "DELETE FROM weekend_packets",
        "UPDATE weekend_packets SET content_hash=repeat('0',64)",
        "DELETE FROM curation_jobs",
        "UPDATE curation_jobs SET status='running'",
    ):
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(text(sql))
    role = "packet_reader_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f"CREATE ROLE {role}"))
        connection.execute(text(f"GRANT SELECT ON weekend_packets, curation_jobs TO {role}"))
    try:
        with engine.begin() as connection:
            connection.execute(text(f"SET LOCAL ROLE {role}"))
            assert connection.execute(text("SELECT id FROM weekend_packets")).all() == []
            assert connection.execute(text("SELECT id FROM curation_jobs")).all() == []
    finally:
        with engine.begin() as connection:
            connection.execute(text(f"DROP OWNED BY {role}"))
            connection.execute(text(f"DROP ROLE {role}"))
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE weekend_packets DISABLE TRIGGER USER"))
        connection.execute(text("UPDATE weekend_packets SET content_hash=repeat('0',64)"))
        connection.execute(text("ALTER TABLE weekend_packets ENABLE TRIGGER USER"))
    with Session(engine) as session:
        with pytest.raises(PacketCorrupt):
            read_packet(session, ids[0], result.packet_id)
        assert read_packet(session, ids[1], result.packet_id) is None


async def test_empty_packet_unknown_usage_and_independent_history(setup):
    engine, ids, contexts, snapshot, policy, now = setup

    class Empty:
        async def curate(self, request):
            return ProviderResponse(
                CurationResult(status="success", recommendations=()), CurationUsage()
            )

    result = await generate_packet(engine, ids[0], snapshot, policy, Empty(), now=now)
    with Session(engine) as session, session.begin():
        packet = read_packet(session, ids[0], result.packet_id)
        assert packet.recommendations == ()
        assert packet.usage.total_tokens is None and packet.usage.estimated_model_cost_usd is None
        write_context(
            session,
            ids[0],
            ProductUserContext.model_validate(OUTDOOR),
            expected_revision_id=contexts[0].revision_id,
        )
    with Session(engine) as session:
        assert read_packet(session, ids[0], result.packet_id) == packet


async def test_foreign_context_cannot_bind_job(setup):
    engine, ids, contexts, snapshot, policy, now = setup
    with pytest.raises(IntegrityError):
        with Session(engine) as session, session.begin():
            session.add(
                CurationJob(
                    id=uuid4(),
                    identity="0" * 64,
                    user_id=ids[0],
                    context_revision_id=contexts[1].revision_id,
                    context_hash=contexts[1].content_hash,
                    snapshot_id=snapshot,
                    snapshot_hash="0" * 64,
                    policy_payload={},
                    status="running",
                    started_at=now,
                )
            )


async def test_full_success_and_personalization_partial(setup):
    engine, ids, contexts, snapshot, policy, now = setup
    from event_radar.models.regional import RegionalWeekendUniverse

    payload = universe().model_dump(mode="json")
    payload["scope"]["research_policy_version"] = "complete-synthetic-v1"
    payload["sources"] = [s for s in payload["sources"] if s["status"] != "failed"]
    for source in payload["sources"]:
        source["status"], source["failure_code"] = "success", None
    payload["diagnostics"], payload["unknowns"] = [], []
    research = RegionalWeekendUniverse.model_validate(payload)
    with Session(engine) as session, session.begin():
        run = begin_regional_research_run(session, research.scope)
        snap = complete_regional_research_run(session, run.id, research, quality_status="success")
        sid = snap.id
    policy = policy.model_copy(update={"research_policy_version": "complete-synthetic-v1"})
    success = await generate_packet(
        engine, ids[0], sid, policy, DeterministicCurationProvider(), now=now
    )
    assert success.status == "success"

    class Partial(DeterministicCurationProvider):
        async def curate(self, request):
            response = await super().curate(request)
            return ProviderResponse(
                response.result.model_copy(update={"status": "partial"}), response.usage
            )

    partial = await generate_packet(engine, ids[1], sid, policy, Partial(), now=now)
    assert partial.status == "partial"
    with Session(engine) as session:
        assert read_packet(session, ids[0], success.packet_id).research_quality == "success"
        assert read_packet(session, ids[1], partial.packet_id).status == "partial"


def test_simultaneous_database_claim(setup):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    engine, ids, contexts, snapshot, policy, now = setup
    barrier = Barrier(2)
    calls = []

    class Concurrent(DeterministicCurationProvider):
        async def curate(self, request):
            calls.append(request.snapshot_id)
            await asyncio.sleep(0.05)
            return await super().curate(request)

    provider = Concurrent()

    def run(_):
        barrier.wait(timeout=5)
        return asyncio.run(generate_packet(engine, ids[0], snapshot, policy, provider, now=now))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert len(calls) == 1
    assert sum(result.packet_id is not None for result in results) >= 1
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(CurationJob)) == 1
        assert session.scalar(select(func.count()).select_from(WeekendPacketRecord)) == 1


async def test_cancelled_attempt_is_durable_and_not_retried(setup):
    engine, ids, contexts, snapshot, policy, now = setup

    class Cancelled:
        calls = 0

        async def curate(self, request):
            self.calls += 1
            raise asyncio.CancelledError

    provider = Cancelled()
    with pytest.raises(asyncio.CancelledError):
        await generate_packet(engine, ids[0], snapshot, policy, provider, now=now)
    result = await generate_packet(engine, ids[0], snapshot, policy, provider, now=now)
    assert result.status == "failed" and result.failure_code == "cancelled"
    assert provider.calls == 1


async def test_recomputed_hash_cannot_hide_invented_packet_facts(setup, monkeypatch, caplog):
    from event_radar.auth.identity import AuthenticatedUser, get_current_user
    from event_radar.models.weekend_packet import digest

    engine, ids, contexts, snapshot, policy, now = setup
    result = await generate_packet(
        engine, ids[0], snapshot, policy, DeterministicCurationProvider(), now=now
    )
    with Session(engine) as session:
        row = session.get(WeekendPacketRecord, result.packet_id)
        payload = row.packet_payload
    payload["recommendations"][0]["facts"]["title"] = "PRIVATE_INVENTED_EVENT"
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE weekend_packets DISABLE TRIGGER USER"))
        connection.execute(
            WeekendPacketRecord.__table__.update().values(
                packet_payload=payload, content_hash=digest(payload)
            )
        )
        connection.execute(text("ALTER TABLE weekend_packets ENABLE TRIGGER USER"))
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=ids[0])
    with TestClient(app) as client:
        response = client.get(f"/api/me/packets/{result.packet_id}")
        assert response.status_code == 503 and response.headers["cache-control"] == "no-store"
        assert response.json()["error"]["code"] == "packet_unavailable"
    assert "PRIVATE_INVENTED_EVENT" not in str([r.getMessage() for r in caplog.records])


async def test_snapshot_tampered_during_curation_fails_publication(setup):
    engine, ids, contexts, snapshot, policy, now = setup

    class Tamper(DeterministicCurationProvider):
        async def curate(self, request):
            with engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE regional_universe_snapshots DISABLE TRIGGER USER")
                )
                connection.execute(
                    text("UPDATE regional_universe_snapshots SET content_hash=repeat('0',64)")
                )
                connection.execute(
                    text("ALTER TABLE regional_universe_snapshots ENABLE TRIGGER USER")
                )
            return await super().curate(request)

    result = await generate_packet(engine, ids[0], snapshot, policy, Tamper(), now=now)
    assert result.failure_code == "snapshot_corrupt"
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(WeekendPacketRecord)) == 0
