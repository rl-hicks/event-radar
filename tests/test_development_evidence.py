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
from event_radar.db.evidence import export_run, export_snapshot
from event_radar.db.models import RegionalResearchRun, RegionalUniverse, RegionalUniverseSnapshot
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


def assert_integrity(exported):
    canonical = json.dumps(
        exported["payload"],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    assert hashlib.sha256(canonical.encode()).hexdigest() == exported["sha256"]


def regional_rows(session):
    # Compare every column, not just counts, across separate committed transactions.
    return [
        session.execute(select(model.__table__).order_by(model.id)).all()
        for model in (RegionalUniverse, RegionalResearchRun, RegionalUniverseSnapshot)
    ]


@pytest.fixture
def exportable_run(database, request):
    from event_radar.models.regional import OperationalDiagnostics
    from event_radar.models.regional_discovery import DiscoveryOperation
    from tests.test_regional_persistence_integration import discovery_summary

    engine, config = database
    command.upgrade(config, "head")
    value = universe()
    status = getattr(request, "param", "failed")
    diagnostic = OperationalDiagnostics(
        stage="complementary_discovery",
        model_id=None,
        status="failed",
        attempts=1,
        attempts_complete=False,
        provider_calls=None,
        input_count=2,
        result_count=0,
        latency_seconds=None,
        tool_calls=None,
        input_tokens=10,
        cached_input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        estimated_model_cost_usd=None,
        usage_complete=False,
        failure_code="unavailable",
        failure_category="provider_transport",
    )
    detail = discovery_summary().model_copy(
        update={
            "stop_reason": "provider_failure",
            "usage": discovery_summary().usage.model_copy(
                update={
                    "model_cost_complete": False,
                    "web_search_calls_complete": False,
                    "attempts_complete": False,
                }
            ),
            "operations": (
                DiscoveryOperation(
                    stage="research",
                    wave=1,
                    task_number=1,
                    failure_code="unavailable",
                    failure_category="provider_transport",
                    reason="request_failed",
                    attempts=1,
                    attempts_complete=False,
                    completed_attempts=0,
                    response_received=None,
                    tool_calls=None,
                    tool_calls_complete=False,
                    latency_seconds=None,
                    input_tokens=10,
                    cached_input_tokens=None,
                    output_tokens=None,
                    total_tokens=None,
                    estimated_model_cost_usd=None,
                    usage_complete=False,
                    model_cost_complete=False,
                ),
            ),
        }
    )
    with Session(engine) as session, session.begin():
        run = begin_regional_research_run(session, value.scope)
        run_id = run.id
        if status == "failed":
            fail_regional_research_run(
                session,
                run_id,
                failure_code="unavailable",
                diagnostics=(diagnostic,),
                discovery_summary=detail,
            )
        else:
            complete_regional_research_run(
                session,
                run_id,
                value,
                quality_status=status,
                failure_code="unavailable" if status == "partial" else None,
                diagnostics=(diagnostic,) if status == "partial" else value.diagnostics,
                discovery_summary=detail if status == "partial" else discovery_summary(),
            )
    return engine, run_id, value, status


@pytest.mark.parametrize("exportable_run", ["failed", "success", "partial"], indirect=True)
def test_run_export_read_only_identity_usage_and_integrity(exportable_run, monkeypatch):
    engine, run_id, value, status = exportable_run

    def forbidden(*args, **kwargs):
        raise AssertionError("Export must not connect to a provider")

    monkeypatch.setattr("socket.socket.connect", forbidden)
    with Session(engine) as session, session.begin():
        session.execute(text("SET TRANSACTION READ ONLY"))
        before = regional_rows(session)
        exported = export_run(session, run_id)
        payload = exported["payload"]
        record = payload["record"]
        assert payload["identity"] == value.scope.identity.model_dump(mode="json")
        assert record["run_id"] == str(run_id) and record["status"] == status
        assert (
            record["requested_as_of"]
            == session.get(RegionalResearchRun, run_id).requested_as_of.isoformat()
        )
        assert record["started_at"] and record["finished_at"]
        if status == "failed":
            assert record["snapshot_id"] is None and payload["snapshot"] is None
            assert len(before[2]) == 0
            assert "universe" not in payload
        else:
            assert payload["snapshot"]["snapshot_id"] == record["snapshot_id"]
            assert payload["snapshot"]["quality_status"] == status
            assert (
                export_snapshot(session, record["snapshot_id"])["payload"]["availability"]
                == "exported"
            )
        if status != "success":
            assert record["failure_code"] == "unavailable"
            op = record["discovery_summary"]["operations"][0]
            assert op["input_tokens"] == 10
            for field in (
                "output_tokens",
                "total_tokens",
                "tool_calls",
                "estimated_model_cost_usd",
            ):
                assert op[field] is None
            assert not op["usage_complete"] and not op["model_cost_complete"]
            assert not op["tool_calls_complete"] and not op["attempts_complete"]
            assert record["diagnostics"][0]["failure_category"] == "provider_transport"
        assert_integrity(exported)
        missing = export_run(session, uuid4())
        assert missing["payload"]["availability"] == "unavailable"
        assert missing["payload"]["record"] is None
        assert_integrity(missing)
        assert regional_rows(session) == before
        wire = json.dumps(exported)
        for excluded in ("api_key", "password", "raw_response", "exception_body", "user_context"):
            assert excluded not in wire
    with Session(engine) as session:
        assert regional_rows(session) == before


@pytest.mark.parametrize("corruption", ["envelope", "stage", "operation", "failure_code"])
def test_run_export_invalid_diagnostics_fail_safely(
    exportable_run, corruption, monkeypatch, capsys, tmp_path
):
    from event_radar import development_evidence as cli

    engine, run_id, _, _ = exportable_run
    sentinel = "RAW_EXCEPTION_SECRET_SENTINEL"
    with Session(engine) as session, session.begin():
        run = session.get(RegionalResearchRun, run_id)
        if corruption == "envelope":
            run.diagnostics_payload = {"raw_response": sentinel}
        elif corruption == "stage":
            run.diagnostics_payload = {"stages": [{"stage": sentinel}]}
        elif corruption == "operation":
            run.discovery_summary = {
                **run.discovery_summary,
                "operations": [{"raw_response": sentinel}],
            }
        else:
            run.failure_code = sentinel
    with Session(engine) as session:
        before = regional_rows(session)
        with pytest.raises(ValueError):
            export_run(session, run_id)
    # Exercise the CLI error boundary with the disposable engine and simulated identity only.
    monkeypatch.setattr(cli, "evidence_url", lambda value: engine.url)
    monkeypatch.setattr(cli, "build_engine", lambda url: engine)
    execute = Session.execute

    def execute_with_identity(self, statement, *args, **kwargs):
        if str(statement) == "SELECT current_database(), current_user":

            class Identity:
                def one(self):
                    return ("event_radar_evidence", "event_radar_evidence")

            return Identity()
        return execute(self, statement, *args, **kwargs)

    monkeypatch.setattr(Session, "execute", execute_with_identity)
    monkeypatch.setattr(
        sys, "argv", ["development_evidence", "export-run", "--run-id", str(run_id)]
    )
    monkeypatch.chdir(tmp_path)
    assert cli.main() == 1
    assert sentinel not in capsys.readouterr().out
    assert not (tmp_path / "output").exists()
    with Session(engine) as session:
        assert regional_rows(session) == before


@pytest.mark.parametrize(
    "args",
    [
        ["export-run", "--snapshot-id"],
        ["export", "--run-id"],
        ["discover-offline", "--run-id"],
    ],
)
def test_export_cli_rejects_wrong_identifier(args):
    result = subprocess.run(
        [sys.executable, "-m", "event_radar.development_evidence", *args, str(uuid4())],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 2
