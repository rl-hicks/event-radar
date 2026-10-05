"""Real PostgreSQL proof for durable Regional Weekend Universe persistence."""

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from alembic.config import Config
from sqlalchemy import Engine, func, select

from alembic import command
from event_radar.db.models import (
    RegionalResearchRun,
    RegionalUniverse,
    RegionalUniverseSnapshot,
)
from event_radar.db.regional import (
    begin_regional_research_run,
    complete_regional_research_run,
    fail_regional_research_run,
    read_current_regional_universe,
)
from event_radar.db.session import build_session_factory, session_scope
from event_radar.models.regional import (
    SONOMA_COUNTY,
    RegionalWeekendUniverse,
    ResearchScope,
    WeekendWindow,
)
from event_radar.models.regional_discovery import (
    AdaptiveDiscoverySummary,
    DiscoveryBudget,
    DiscoveryBudgetUsage,
    DiscoveryWaveRecord,
)

FIXTURE = Path(__file__).parent / "fixtures/regional/universe.json"
PACIFIC = ZoneInfo("America/Los_Angeles")


def fixture_universe() -> RegionalWeekendUniverse:
    return RegionalWeekendUniverse.model_validate_json(FIXTURE.read_text())


def discovery_summary() -> AdaptiveDiscoverySummary:
    return AdaptiveDiscoverySummary(
        stop_reason="planner_stopped",
        budget=DiscoveryBudget(
            max_waves=3,
            max_model_calls=10,
            max_web_search_calls=12,
            max_model_cost_usd=Decimal("5"),
        ),
        usage=DiscoveryBudgetUsage(
            waves=1,
            model_calls=4,
            web_search_calls=3,
            estimated_model_cost_usd=Decimal("0.06"),
            model_cost_complete=True,
        ),
        waves=(
            DiscoveryWaveRecord(
                wave=1,
                planned_task_ids=("research-community",),
                verified_candidate_count=1,
                incremental_opportunity_count=1,
                duplicate_count=0,
                source_lead_count=1,
            ),
        ),
        source_leads=(),
    )


def changed_universe(
    value: RegionalWeekendUniverse,
    *,
    detail: str,
) -> RegionalWeekendUniverse:
    payload = value.model_dump(mode="json", exclude_none=False)
    payload["unknowns"] = [
        *payload["unknowns"],
        {
            "kind": "source_coverage",
            "detail": detail,
        },
    ]
    return RegionalWeekendUniverse.model_validate(payload)


def changed_provenance(value: RegionalWeekendUniverse) -> RegionalWeekendUniverse:
    payload = value.model_dump(mode="json", exclude_none=False)
    payload["opportunities"][0]["evidence"][0]["summary"] = (
        "Updated synthetic public evidence from the same source."
    )
    return RegionalWeekendUniverse.model_validate(payload)


def second_weekend() -> RegionalWeekendUniverse:
    scope = ResearchScope(
        region=SONOMA_COUNTY,
        window=WeekendWindow(
            friday=date(2026, 10, 9),
            timezone="America/Los_Angeles",
        ),
        research_policy_version="regional-v1",
        as_of=datetime(2026, 10, 9, 13, 0, tzinfo=PACIFIC),
    )
    return RegionalWeekendUniverse(
        scope=scope,
        opportunities=(),
        sources=(),
        exclusions=(),
        diagnostics=(),
        unknowns=(),
    )


def count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_regional_universe_persistence_replay_and_readback(
    database: tuple[Engine, Config],
) -> None:
    engine, config = database
    command.upgrade(config, "head")
    factory = build_session_factory(engine)
    value = fixture_universe()

    with session_scope(factory) as session:
        first_run = begin_regional_research_run(session, value.scope)
        first_snapshot = complete_regional_research_run(
            session,
            first_run.id,
            value,
            quality_status="success",
            diagnostics=value.diagnostics,
            discovery_summary=discovery_summary(),
        )
        first_snapshot_id = first_snapshot.id

    with session_scope(factory) as session:
        second_run = begin_regional_research_run(session, value.scope)
        second_snapshot = complete_regional_research_run(
            session,
            second_run.id,
            value,
            quality_status="success",
            diagnostics=value.diagnostics,
            discovery_summary=discovery_summary(),
        )
        assert second_snapshot.id == first_snapshot_id

    with session_scope(factory) as session:
        persisted = read_current_regional_universe(session, value.scope.identity)
        assert persisted is not None
        assert persisted.snapshot_id == first_snapshot_id
        assert persisted.quality_status == "success"
        assert persisted.universe == value
        assert persisted.discovery_summary is not None
        assert persisted.discovery_summary["stop_reason"] == "planner_stopped"
        assert count(session, RegionalUniverse) == 1
        assert count(session, RegionalUniverseSnapshot) == 1
        assert count(session, RegionalResearchRun) == 2
        runs = session.scalars(select(RegionalResearchRun)).all()
        assert {run.status for run in runs} == {"success"}
        assert all(run.snapshot_id == first_snapshot_id for run in runs)
        assert all(run.diagnostics_payload is not None for run in runs)

        wire = json.dumps(persisted.universe.model_dump(mode="json"))
        for prohibited in (
            "user_context",
            "permanent_directions",
            "temporary_directions",
            "telegram_chat_id",
            "drive_friction_from_santa_rosa",
            "why_it_may_fit",
            "disposition",
        ):
            assert prohibited not in wire


def test_partial_and_failed_retry_preserve_prior_success(
    database: tuple[Engine, Config],
) -> None:
    engine, config = database
    command.upgrade(config, "head")
    factory = build_session_factory(engine)
    value = fixture_universe()

    with session_scope(factory) as session:
        run = begin_regional_research_run(session, value.scope)
        success = complete_regional_research_run(
            session,
            run.id,
            value,
            quality_status="success",
        )
        success_id = success.id

    partial_value = changed_universe(
        value,
        detail="One complementary research source timed out during retry.",
    )
    with session_scope(factory) as session:
        run = begin_regional_research_run(session, partial_value.scope)
        partial = complete_regional_research_run(
            session,
            run.id,
            partial_value,
            quality_status="partial",
            failure_code="timeout",
        )
        assert partial.id != success_id
        assert partial.quality_status == "partial"

    with session_scope(factory) as session:
        persisted = read_current_regional_universe(session, value.scope.identity)
        assert persisted is not None
        assert persisted.snapshot_id == success_id
        assert persisted.quality_status == "success"

    with session_scope(factory) as session:
        run = begin_regional_research_run(session, value.scope)
        failed_run_id = run.id
        fail_regional_research_run(
            session,
            run.id,
            failure_code="unavailable",
        )

    with session_scope(factory) as session:
        persisted = read_current_regional_universe(session, value.scope.identity)
        assert persisted is not None
        assert persisted.snapshot_id == success_id
        failed = session.get(RegionalResearchRun, failed_run_id)
        assert failed is not None
        assert failed.status == "failed"
        assert failed.snapshot_id is None
        assert failed.failure_code == "unavailable"
        assert count(session, RegionalUniverseSnapshot) == 2
        assert count(session, RegionalResearchRun) == 3


def test_changed_provenance_and_distinct_weekends_preserve_history(
    database: tuple[Engine, Config],
) -> None:
    engine, config = database
    command.upgrade(config, "head")
    factory = build_session_factory(engine)
    value = fixture_universe()
    revised = changed_provenance(value)

    with session_scope(factory) as session:
        first_run = begin_regional_research_run(session, value.scope)
        first = complete_regional_research_run(
            session,
            first_run.id,
            value,
            quality_status="success",
        )
        first_id = first.id

    with session_scope(factory) as session:
        revised_run = begin_regional_research_run(session, revised.scope)
        revised_snapshot = complete_regional_research_run(
            session,
            revised_run.id,
            revised,
            quality_status="success",
        )
        assert revised_snapshot.id != first_id
        revised_id = revised_snapshot.id

    other = second_weekend()
    with session_scope(factory) as session:
        other_run = begin_regional_research_run(session, other.scope)
        complete_regional_research_run(
            session,
            other_run.id,
            other,
            quality_status="success",
        )

    with session_scope(factory) as session:
        current = read_current_regional_universe(session, value.scope.identity)
        assert current is not None
        assert current.snapshot_id == revised_id
        assert current.universe == revised

        original = session.get(RegionalUniverseSnapshot, first_id)
        assert original is not None
        assert RegionalWeekendUniverse.model_validate(original.universe_payload) == value

        other_current = read_current_regional_universe(session, other.scope.identity)
        assert other_current is not None
        assert other_current.universe == other
        assert count(session, RegionalUniverse) == 2
        assert count(session, RegionalUniverseSnapshot) == 3


def test_regional_attempt_creation_rolls_back_transactionally(
    database: tuple[Engine, Config],
) -> None:
    engine, config = database
    command.upgrade(config, "head")
    factory = build_session_factory(engine)
    value = fixture_universe()
    run_id = uuid4()

    with pytest.raises(RuntimeError, match="force rollback"):
        with session_scope(factory) as session:
            begin_regional_research_run(
                session,
                value.scope,
                run_id=run_id,
            )
            raise RuntimeError("force rollback")

    with session_scope(factory) as session:
        assert session.get(RegionalResearchRun, run_id) is None
        assert count(session, RegionalUniverse) == 0
        assert count(session, RegionalResearchRun) == 0
