"""Scheduled re-delivery never repeats provider work, even after failure."""

import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from event_radar.db.evidence import export_run
from event_radar.db.regional import begin_regional_research_run, read_current_regional_universe
from event_radar.shared.spend_guard import WholeWorkerLimits, guard_dependencies
from event_radar.shared.worker import run_regional_worker
from event_radar.shared_schedule import database_preflight, retained_evidence
from tests.test_development_evidence import assert_integrity, regional_rows
from tests.test_shared_worker_integration import budget, counts, scope
from tests.test_shared_worker_integration import worker as worker


@pytest.mark.parametrize("mode", ["success", "partial", "failed", "abandoned"])
async def test_scheduled_attempt_is_never_automatically_retried(worker, mode):
    deps, source, semantics, discovery = worker
    if mode == "abandoned":
        with Session(deps.engine) as session, session.begin():
            begin_regional_research_run(session, scope())
    else:
        if mode == "partial":
            from event_radar.shared.collection import RegionalSourceFailure

            source.failure = RegionalSourceFailure("unavailable")
        if mode == "failed":

            async def fatal(*args, **kwargs):
                raise RuntimeError("RAW_SECRET_SENTINEL")

            source.collect = fatal
        first = await run_regional_worker(scope(), deps, budget=budget(), attempt_once=True)
        assert first.status == mode
    before_calls = (source.calls, len(semantics.calls), len(discovery.calls))
    with Session(deps.engine) as session:
        before = regional_rows(session)
    result = await run_regional_worker(scope(), deps, budget=budget(), attempt_once=True)
    assert result.status == ("replayed" if mode == "success" else "blocked")
    assert result.run_id
    assert (source.calls, len(semantics.calls), len(discovery.calls)) == before_calls
    with Session(deps.engine) as session, session.begin():
        session.execute(text("SET TRANSACTION READ ONLY"))
        assert regional_rows(session) == before
        exported = export_run(session, result.run_id)
        assert_integrity(exported)
        assert "RAW_SECRET_SENTINEL" not in str(exported)
        assert exported["payload"]["record"]["status"] == (
            "running" if mode == "abandoned" else mode
        )
    assert counts(deps)[2] == 1
    evidence = retained_evidence(deps.engine, scope())
    assert_integrity(evidence)
    assert len(evidence["payload"]["runs"]) == 1


async def test_scheduled_concurrency_and_no_refresh(worker):
    deps, source, _, _ = worker
    source.entered, source.release = asyncio.Event(), asyncio.Event()
    first = asyncio.create_task(
        run_regional_worker(scope(), deps, budget=budget(), attempt_once=True)
    )
    await source.entered.wait()
    second = await run_regional_worker(scope(), deps, budget=budget(), attempt_once=True)
    assert second.status == "busy"
    source.release.set()
    assert (await first).status == "success"
    assert source.calls == 1
    with pytest.raises(ValueError):
        await run_regional_worker(scope(), deps, budget=budget(), attempt_once=True, refresh=True)


@pytest.mark.parametrize(
    "limit,expected_discovery",
    [
        (2, ["plan"]),
        (5, ["plan", "research", "verify", "plan"]),
    ],
)
async def test_whole_worker_limit_includes_initial_incremental_and_discovery(
    worker,
    limit,
    expected_discovery,
):
    deps, source, semantics, discovery = worker
    bounded = guard_dependencies(
        deps, WholeWorkerLimits(max_model_calls=limit, max_estimated_model_cost_usd=Decimal("1"))
    )
    result = await run_regional_worker(scope(), bounded, budget=budget(), attempt_once=True)
    assert result.status == "partial"
    assert len(semantics.calls) == 1
    assert discovery.calls == expected_discovery
    with Session(deps.engine) as session:
        saved = read_current_regional_universe(session, scope().identity)
        assert saved.quality_status == "partial"
        assert any(d.failure_category == "configuration" for d in saved.universe.diagnostics)


def test_database_preflight_and_missing_evidence(worker):
    deps, *_ = worker
    database_preflight(deps.engine, database="event_radar_test", user="event_radar_test")
    with pytest.raises(ValueError):
        database_preflight(deps.engine, database="wrong", user="event_radar_test")
    missing = retained_evidence(deps.engine, scope())
    assert missing["payload"]["availability"] == "unavailable"
    assert missing["payload"]["runs"] == []


@pytest.mark.parametrize("failure", [False, True])
async def test_scheduler_cli_receipt_and_exports_are_public(worker, tmp_path, monkeypatch, failure):
    import json
    from pathlib import Path

    from sqlalchemy import URL

    from event_radar.shared_schedule import main

    deps, _, semantics, _ = worker
    config_text = Path("config/shared-research-envelope.json").read_text()
    config = tmp_path / "config.json"
    config.write_text(config_text)
    monkeypatch.chdir(tmp_path)
    semantics.fail = failure
    approved_scope = scope().model_copy(update={"research_policy_version": "e1-weekly-sonoma-v1"})
    monkeypatch.setattr("event_radar.shared_schedule.scheduled_scope", lambda *args: approved_scope)
    monkeypatch.setattr("event_radar.shared_schedule.build_engine", lambda *args: deps.engine)
    monkeypatch.setenv("EVENT_RADAR_SCHEDULE_APPROVED", "true")
    monkeypatch.setenv("EVENT_RADAR_RESEARCH_EXPECTED_HOST", "database.example.org")
    monkeypatch.setenv("EVENT_RADAR_RESEARCH_EXPECTED_DATABASE", "event_radar_test")
    monkeypatch.setenv("EVENT_RADAR_RESEARCH_EXPECTED_USER", "event_radar_test")
    monkeypatch.setenv("EVENT_RADAR_RESEARCH_OPENAI_API_KEY", "SECRET_SENTINEL")
    monkeypatch.setenv(
        "EVENT_RADAR_RESEARCH_DATABASE_URL",
        URL.create(
            "postgresql+psycopg",
            username="worker",
            password="SECRET_SENTINEL",
            host="database.example.org",
            port=5432,
            database="postgres",
            query={"sslmode": "verify-full"},
        ).render_as_string(hide_password=False),
    )

    # Main is sync: fake execution returns a precomputed deterministic worker outcome.
    result = await run_regional_worker(
        approved_scope,
        guard_dependencies(
            deps,
            WholeWorkerLimits(max_model_calls=24, max_estimated_model_cost_usd=Decimal("0.25")),
        ),
        budget=budget(),
        attempt_once=True,
    )

    async def fake_execute(config, *, attempt_once, whole_worker_limits):
        assert attempt_once and whole_worker_limits.max_model_calls == 24
        assert config.scope == approved_scope
        return result

    monkeypatch.setattr("event_radar.shared_runtime.execute_real", fake_execute)
    # Run the synchronous CLI in a thread, outside this test's active asyncio loop.
    code = await asyncio.to_thread(
        main,
        [
            "execute",
            "--config",
            str(config),
            "--triggered-at",
            "2026-10-08T12:15:00-07:00",
            "--acknowledge-live-run",
        ],
    )
    assert code == (2 if failure else 0)
    files = list((tmp_path / "output/development-evidence").glob("schedule-*.json"))
    assert len(files) == 2
    for path in files:
        wire = path.read_text()
        assert "SECRET_SENTINEL" not in wire
        assert_integrity(json.loads(wire))


async def test_scheduled_block_preserves_last_good_after_partial_refresh(worker):
    deps, source, semantics, discovery = worker
    first = await run_regional_worker(scope(), deps, budget=budget(), attempt_once=True)
    semantics.fail = True
    partial = await run_regional_worker(scope(), deps, budget=budget(), refresh=True)
    assert partial.status == "partial"
    before_calls = (source.calls, len(semantics.calls), len(discovery.calls))
    with Session(deps.engine) as session:
        before = regional_rows(session)
        assert (
            read_current_regional_universe(session, scope().identity).snapshot_id
            == first.snapshot_id
        )
    blocked = await run_regional_worker(scope(), deps, budget=budget(), attempt_once=True)
    assert blocked.status == "blocked" and blocked.run_id == partial.run_id
    assert before_calls == (source.calls, len(semantics.calls), len(discovery.calls))
    with Session(deps.engine) as session:
        assert regional_rows(session) == before
        assert (
            read_current_regional_universe(session, scope().identity).snapshot_id
            == first.snapshot_id
        )


async def test_unknown_usage_stops_all_following_models_and_is_exported(worker):
    from dataclasses import replace

    from event_radar.models.token_usage import TokenUsage
    from event_radar.shared_schedule import accounting_review

    deps, _, semantics, discovery = worker
    original = semantics.analyze

    async def unknown(request, *, correction=None):
        response = await original(request, correction=correction)
        return replace(response, usage=TokenUsage())

    semantics.analyze = unknown
    bounded = guard_dependencies(
        deps, WholeWorkerLimits(max_model_calls=24, max_estimated_model_cost_usd=Decimal("1"))
    )
    result = await run_regional_worker(scope(), bounded, budget=budget(), attempt_once=True)
    assert result.status == "partial"
    assert len(semantics.calls) == 1
    assert discovery.calls == []
    evidence = retained_evidence(deps.engine, scope())
    assert_integrity(evidence)
    accounting = accounting_review(evidence)
    assert accounting["incomplete"]
    assert accounting["billing_total_usd"] is None
    stages = evidence["payload"]["runs"][0]["payload"]["record"]["diagnostics"]
    assert any(stage["estimated_model_cost_usd"] is None for stage in stages)


def test_local_target_denied_and_wrong_migration_rejected(worker, tmp_path, monkeypatch):
    from pathlib import Path

    from event_radar.shared_schedule import main

    deps, *_ = worker
    config = tmp_path / "config.json"
    config.write_text(Path("config/shared-research-envelope.json").read_text())
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EVENT_RADAR_SCHEDULE_APPROVED", "true")
    monkeypatch.setattr("event_radar.shared_schedule.scheduled_scope", lambda *args: scope())
    # Target parsing is independently tested; use test engine, never contact remote DB.
    monkeypatch.setattr(
        "event_radar.shared_schedule.research_database_url", lambda value: deps.engine.url
    )
    monkeypatch.setenv("EVENT_RADAR_RESEARCH_EXPECTED_HOST", deps.engine.url.host)
    # This target is intentionally denied as local before connecting.
    calls = []
    monkeypatch.setattr(
        "event_radar.shared_schedule.build_engine", lambda *args: calls.append("engine")
    )
    assert (
        main(
            [
                "execute",
                "--config",
                str(config),
                "--triggered-at",
                "2026-10-08T12:00:00-07:00",
                "--acknowledge-live-run",
            ]
        )
        == 2
    )
    assert calls == []
    # Independently verify an unexpected migration is rejected on the disposable database.
    with Session(deps.engine) as session:
        assert (
            session.scalar(text("SELECT version_num FROM alembic_version"))
            == "0005_packet_delivery"
        )
    with deps.engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = 'unapproved_revision'"))
    try:
        with pytest.raises(ValueError):
            database_preflight(deps.engine, database="event_radar_test", user="event_radar_test")
    finally:
        with deps.engine.begin() as connection:
            connection.execute(
                text("UPDATE alembic_version SET version_num = '0005_packet_delivery'")
            )
