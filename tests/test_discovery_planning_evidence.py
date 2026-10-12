"""Accepted planner decisions are bounded public evidence, not raw provider output."""

import json

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic import command
from event_radar.db.evidence import export_run, export_snapshot
from event_radar.db.models import RegionalResearchRun
from event_radar.db.regional import (
    begin_regional_research_run,
    complete_regional_research_run,
    fail_regional_research_run,
    read_regional_snapshot,
)
from event_radar.models.regional_discovery import AdaptiveDiscoverySummary, DiscoveryPlan
from event_radar.shared.discovery import DiscoveryProviderResponse, run_adaptive_discovery
from tests.test_adaptive_regional_discovery import (
    Planner,
    Researcher,
    Verifier,
    budget,
    collection,
    plan,
    universe,
)
from tests.test_development_evidence import assert_integrity, regional_rows


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Network or unrelated pipeline operation attempted")

    monkeypatch.setattr("socket.socket.connect", forbidden)
    monkeypatch.setattr("event_radar.shared.collection.collect_registered_sources", forbidden)
    monkeypatch.setattr("event_radar.shared.semantic_analysis.enrich_regional_semantics", forbidden)


class FixedPlanner(Planner):
    def __init__(self, accepted):
        super().__init__()
        self.accepted = accepted

    async def plan(self, context):
        self.calls.append(context)
        return DiscoveryProviderResponse(value=self.accepted)


async def discover(planner, *, failure_callback=None):
    return await run_adaptive_discovery(
        universe().scope,
        collection(),
        planner,
        Researcher(),
        Verifier(),
        budget=budget(),
        on_failure=failure_callback,
        observed_at=universe().scope.as_of,
    )


@pytest.mark.parametrize(
    "mode,reason",
    [
        ("continue", "planner_stopped"),
        ("stop_empty", "planner_stopped"),
        ("stop_gaps", "planner_stopped"),
        ("no_tasks", "no_tasks"),
    ],
)
async def test_accepted_decisions_and_stop_semantics(mode, reason):
    accepted = plan().model_dump()
    if mode != "continue":
        accepted["tasks"] = ()
        accepted["should_continue"] = mode == "no_tasks"
        if mode == "stop_empty":
            accepted["gaps"] = ()
    planner = (
        Planner() if mode == "continue" else FixedPlanner(DiscoveryPlan.model_validate(accepted))
    )
    result = await discover(planner)
    summary = result.summary
    assert summary.stop_reason == reason
    decisions = summary.planning_decisions
    assert decisions is not None
    assert [d.wave for d in decisions] == ([1, 2] if mode == "continue" else [1])
    assert decisions[0].plan == DiscoveryPlan.model_validate(accepted)
    if mode == "continue":
        assert decisions[1].plan == plan(should_continue=False)
        assert summary.waves[0].incremental_opportunity_count == 1
    else:
        assert not summary.waves
        assert len(summary.operations) == 1
    # The only planner input is the existing neutral scope, coverage and inventory.
    assert set(planner.calls[0].model_dump()) == {"scope", "coverage", "existing_opportunities"}


async def test_no_accepted_plan_on_provider_failure():
    result = await discover(Planner(fail=True))
    assert result.summary.planning_decisions == ()
    assert result.summary.stop_reason == "provider_failure"


async def test_fatal_failure_retains_earlier_accepted_plan():
    class FatalSecondPlanner(Planner):
        async def plan(self, context):
            if self.calls:
                raise RuntimeError("RAW_PRIVATE_SENTINEL")
            return await super().plan(context)

    captured = []
    with pytest.raises(RuntimeError):
        await discover(FatalSecondPlanner(), failure_callback=lambda *args: captured.append(args))
    summary = captured[0][1]
    assert [d.wave for d in summary.planning_decisions] == [1]
    assert "RAW_PRIVATE_SENTINEL" not in summary.model_dump_json()


@pytest.mark.parametrize(
    "field",
    [
        "rationale",
        "gap_description",
        "gap_rationale",
        "search_goal",
        "target_area",
        "opportunity_type",
        "gaps",
        "tasks",
        "gap_ids",
        "private_extra",
    ],
)
def test_plan_bounds_and_private_fields(field):
    value = plan().model_dump(mode="json")
    if field == "rationale":
        value[field] = "x" * 2049
    elif field.startswith("gap_") and field != "gap_ids":
        value["gaps"][0][field.removeprefix("gap_")] = "x" * 2049
    elif field in ("search_goal", "target_area", "opportunity_type"):
        value["tasks"][0][field] = "x" * (2049 if field == "search_goal" else 129)
    elif field in ("gaps", "tasks"):
        value[field] = [
            dict(value[field][0], **{("gap_id" if field == "gaps" else "task_id"): f"id-{i}"})
            for i in range(33)
        ]
    elif field == "gap_ids":
        value["tasks"][0][field] *= 33
    else:
        value["private_context"] = "PRIVATE_SENTINEL"
    with pytest.raises(ValidationError):
        DiscoveryPlan.model_validate(value)


async def test_injected_validation_bypass_is_not_retained():
    invalid = plan().model_copy(update={"rationale": "x" * 2049})
    result = await discover(FixedPlanner(invalid))
    assert result.summary.planning_decisions == ()
    assert result.summary.stop_reason == "provider_failure"
    assert result.summary.operations[-1].reason == "local_result_invalid"


async def test_legacy_summary_and_wave_validation():
    result = await discover(Planner())
    data = result.summary.model_dump(mode="json")
    data.pop("planning_decisions")
    assert AdaptiveDiscoverySummary.model_validate(data).planning_decisions is None
    data["planning_decisions"] = [
        d.model_dump(mode="json") for d in reversed(result.summary.planning_decisions)
    ]
    with pytest.raises(ValidationError):
        AdaptiveDiscoverySummary.model_validate(data)


@pytest.mark.parametrize("status", ["success", "partial", "failed", "legacy"])
async def test_database_readback_and_both_export_envelopes(database, status):
    engine, config = database
    command.upgrade(config, "head")
    base = universe()
    result = await discover(Planner())
    summary = result.summary
    if status == "legacy":
        summary = AdaptiveDiscoverySummary.model_validate(
            summary.model_dump(exclude={"planning_decisions"})
        )
    with Session(engine) as session, session.begin():
        run = begin_regional_research_run(session, base.scope)
        run_id = run.id
        snapshot_id = None
        if status == "failed":
            fail_regional_research_run(
                session,
                run.id,
                failure_code="unavailable",
                diagnostics=(),
                discovery_summary=summary,
            )
        else:
            snapshot = complete_regional_research_run(
                session,
                run.id,
                base,
                quality_status="partial" if status == "partial" else "success",
                failure_code="unavailable" if status == "partial" else None,
                diagnostics=base.diagnostics,
                discovery_summary=summary,
            )
            snapshot_id = snapshot.id
        # Reproduce old stored JSON, not merely the new model's null default.
        if status == "legacy":
            old = summary.model_dump(mode="json", exclude={"planning_decisions"})
            run.discovery_summary = old
            snapshot.discovery_summary = old
    with Session(engine) as session, session.begin():
        session.execute(text("SET TRANSACTION READ ONLY"))
        before = regional_rows(session)
        exported = export_run(session, run_id)
        assert_integrity(exported)
        wire = exported["payload"]["record"]["discovery_summary"]
        assert wire["planning_decisions"] == summary.model_dump(mode="json")["planning_decisions"]
        assert (
            session.get(RegionalResearchRun, run_id).discovery_summary.get("planning_decisions")
            == wire["planning_decisions"]
        )
        if snapshot_id:
            stored = read_regional_snapshot(session, snapshot_id)
            assert stored.universe == base
            snapshot_export = export_snapshot(session, snapshot_id)
            assert_integrity(snapshot_export)
            assert snapshot_export["payload"]["discovery_summary"] == wire
            assert (
                snapshot_export["payload"]["related_identity_runs"][0]["discovery_summary"] == wire
            )
        assert regional_rows(session) == before
        assert "PRIVATE_SENTINEL" not in json.dumps(exported)


@pytest.mark.parametrize("target", ["run", "snapshot"])
async def test_corrupt_stored_plan_fails_export_closed(database, target):
    engine, config = database
    command.upgrade(config, "head")
    base = universe()
    result = await discover(Planner())
    with Session(engine) as session, session.begin():
        run = begin_regional_research_run(session, base.scope)
        snapshot = complete_regional_research_run(
            session,
            run.id,
            base,
            quality_status="success",
            diagnostics=base.diagnostics,
            discovery_summary=result.summary,
        )
        run_id, snapshot_id = run.id, snapshot.id
        corrupt = result.summary.model_dump(mode="json")
        corrupt["planning_decisions"][0]["plan"]["private_context"] = "PRIVATE_SENTINEL"
        record = run if target == "run" else snapshot
        record.discovery_summary = corrupt
    with Session(engine) as session, session.begin():
        session.execute(text("SET TRANSACTION READ ONLY"))
        before = regional_rows(session)
        with pytest.raises(ValidationError):
            (
                export_run(session, run_id)
                if target == "run"
                else export_snapshot(session, snapshot_id)
            )
        assert regional_rows(session) == before
