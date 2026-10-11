"""Offline diagnostic and export regressions on the guarded disposable database."""

import hashlib
import json
import os
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import URL, func, select, text
from sqlalchemy.orm import Session

from alembic import command
from event_radar.db.evidence import export_snapshot
from event_radar.db.models import RegionalResearchRun, RegionalUniverseSnapshot
from event_radar.db.regional import (
    begin_regional_research_run,
    complete_regional_research_run,
    fail_regional_research_run,
    read_regional_snapshot,
)
from event_radar.development_evidence import evidence_url
from event_radar.shared.discovery import DiscoveryProviderFailure
from event_radar.shared.discovery_only import diagnose_snapshot
from tests.database_safety import isolated_test_url
from tests.test_adaptive_regional_discovery import (
    Planner,
    Researcher,
    Verifier,
    budget,
    duplicate_candidate,
    universe,
)


@pytest.fixture
def stored(database):
    engine, config = database
    command.upgrade(config, "head")
    value = universe()
    with Session(engine) as session, session.begin():
        run = begin_regional_research_run(session, value.scope)
        snapshot = complete_regional_research_run(
            session,
            run.id,
            value,
            quality_status="success",
            diagnostics=value.diagnostics,
        )
        snapshot_id = snapshot.id
    return engine, snapshot_id, value


@pytest.mark.parametrize("mode", ["added_duplicate", "rejected", "duplicate_only", "empty"])
async def test_read_only_discovery(stored, monkeypatch, mode):
    engine, snapshot_id, base = stored

    def forbidden(*args, **kwargs):
        raise AssertionError("Unexpected collection, semantics, or network")

    monkeypatch.setattr("socket.socket.connect", forbidden)
    monkeypatch.setattr("event_radar.shared.collection.collect_registered_sources", forbidden)
    monkeypatch.setattr("event_radar.shared.semantic_analysis.enrich_regional_semantics", forbidden)
    planner, researcher, verifier = Planner(), Researcher(), Verifier(reject_all=mode == "rejected")
    if mode == "duplicate_only":
        researcher.candidates = (duplicate_candidate(),)
    if mode == "empty":
        researcher.candidates = ()
    with Session(engine) as session, session.begin():
        session.execute(text("SET TRANSACTION READ ONLY"))
        before = export_snapshot(session, snapshot_id)
        result = await diagnose_snapshot(
            session,
            snapshot_id,
            planner,
            researcher,
            verifier,
            budget=budget(),
        )
        assert export_snapshot(session, snapshot_id) == before
        assert read_regional_snapshot(session, snapshot_id).universe == base
        assert session.scalar(select(func.count()).select_from(RegionalResearchRun)) == 1
        assert session.scalar(select(func.count()).select_from(RegionalUniverseSnapshot)) == 1
    assert result["base_snapshot_id"] == str(snapshot_id)
    assert not result["weekly_worker_completed"]
    assert planner.calls[0].scope == base.scope
    assert planner.calls[0].existing_opportunities == base.opportunities
    assert planner.calls[0].coverage.searched_source_classes == ()
    assert researcher.calls
    summary = result["discovery_summary"]
    if mode == "added_duplicate":
        assert len(result["new_opportunities"]) == 1
        assert summary["waves"][0]["duplicate_count"] == 1
        assert result["remaining_gaps_complete"]
    else:
        assert not result["new_opportunities"]
        assert summary["stop_reason"] == "no_incremental_candidates"
    if mode == "rejected":
        assert all(not d["verified"] for d in result["verification_results"][0]["decisions"])
        assert all(
            d["rejection_code"] == "unverifiable"
            for d in result["verification_results"][0]["decisions"]
        )


@pytest.mark.parametrize("stage", ["plan", "research", "verify"])
@pytest.mark.parametrize("fatal", [False, True])
async def test_failure_accounting_and_export(stored, stage, fatal):
    engine, snapshot_id, base = stored
    planner, researcher, verifier = Planner(), Researcher(), Verifier()

    async def fail(*args, **kwargs):
        if fatal:
            raise RuntimeError("RAW_PROVIDER_SECRET_SENTINEL")
        raise DiscoveryProviderFailure(
            "unavailable",
            category="provider_transport",
            reason="request_failed",
        )

    setattr({"plan": planner, "research": researcher, "verify": verifier}[stage], stage, fail)
    with Session(engine) as session, session.begin():
        result = await diagnose_snapshot(
            session,
            snapshot_id,
            planner,
            researcher,
            verifier,
            budget=budget(),
        )
        detail = result["discovery_summary"]
        assert detail["stop_reason"] == "provider_failure"
        assert not detail["usage"]["model_cost_complete"]
        assert detail["operations"][-1]["total_tokens"] is None
        assert detail["operations"][-1]["estimated_model_cost_usd"] is None
        assert "RAW_PROVIDER_SECRET_SENTINEL" not in json.dumps(result)
        from event_radar.models.regional import OperationalDiagnostics
        from event_radar.models.regional_discovery import AdaptiveDiscoverySummary

        run = begin_regional_research_run(session, base.scope)
        fail_regional_research_run(
            session,
            run.id,
            failure_code="unavailable",
            diagnostics=(OperationalDiagnostics.model_validate(result["diagnostics"]),),
            discovery_summary=AdaptiveDiscoverySummary.model_validate(detail),
        )
    with Session(engine) as session, session.begin():
        session.execute(text("SET TRANSACTION READ ONLY"))
        exported = export_snapshot(session, snapshot_id)
        payload = exported["payload"]
        assert payload["universe"] == base.model_dump(mode="json")
        assert len(payload["related_identity_runs"]) == 2
        assert payload["related_identity_runs"][-1]["discovery_summary"] == detail
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        assert hashlib.sha256(canonical.encode()).hexdigest() == exported["sha256"]
        assert payload["related_identity_runs"][-1]["diagnostics"][0]["failure_category"]
        assert export_snapshot(session, uuid4())["payload"]["availability"] == "unavailable"


def test_corrupt_snapshot_fails_closed(stored):
    engine, snapshot_id, _ = stored
    with Session(engine) as session, session.begin():
        snapshot = session.get(RegionalUniverseSnapshot, snapshot_id)
        snapshot.content_hash = "0" * 64
    with Session(engine) as session, pytest.raises(ValueError, match="hash mismatch"):
        export_snapshot(session, snapshot_id)


def test_database_targets_are_disjoint(monkeypatch):
    for name in tuple(os.environ):
        if name.startswith("PG"):
            monkeypatch.delenv(name)
    target = URL.create(
        "postgresql+psycopg",
        username="event_radar_evidence",
        password="unused",
        host="127.0.0.1",
        port=55433,
        database="event_radar_evidence",
    ).render_as_string(hide_password=False)
    assert evidence_url(target).database == "event_radar_evidence"
    with pytest.raises(ValueError):
        isolated_test_url(target)
    for bad in (
        target.replace("127.0.0.1", "remote.example"),
        target.replace("55433", "55432"),
        target + "?hostaddr=192.0.2.1",
    ):
        with pytest.raises(ValueError):
            evidence_url(bad)
    monkeypatch.setenv("PGHOSTADDR", "192.0.2.1")
    with pytest.raises(ValueError):
        evidence_url(target)


def test_offline_process_guard():
    code = """
from event_radar.development_evidence import install_offline_guard
install_offline_guard()
import socket
for operation in (
    lambda: __import__('openai'),
    lambda: socket.create_connection(('example.org', 443)),
    lambda: __import__('event_radar.shared_runtime'),
):
    try:
        operation()
    except RuntimeError:
        pass
    else:
        raise AssertionError('offline guard failed')
"""
    subprocess.run([sys.executable, "-c", code], check=True, timeout=20)
