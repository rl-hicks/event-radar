"""WP7 proofs use the guarded, disposable real PostgreSQL fixture."""

import asyncio
import os
import subprocess
import sys
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from alembic import command
from event_radar.db.models import RegionalResearchRun, RegionalUniverse, RegionalUniverseSnapshot
from event_radar.db.regional import read_current_regional_universe
from event_radar.db.session import build_session_factory
from event_radar.models.regional import SONOMA_COUNTY, ResearchScope, WeekendWindow
from event_radar.models.regional_discovery import DiscoveryBudget, DiscoveryPlan
from event_radar.shared.collection import (
    RegionalSourceFailure,
    RegionalSourceResult,
    SourceRegistration,
    SourceRegistry,
)
from event_radar.shared.discovery import DiscoveryProviderResponse
from event_radar.shared.semantic_analysis import SemanticProviderFailure
from event_radar.shared.synthetic import (
    SyntheticDiscovery,
    SyntheticSemantics,
    SyntheticSource,
    synthetic_usage,
)
from event_radar.shared.worker import ResearchBudget, WorkerDependencies, run_regional_worker


def scope(friday=date(2026, 10, 9)):
    return ResearchScope(
        region=SONOMA_COUNTY,
        window=WeekendWindow(friday=friday, timezone=SONOMA_COUNTY.timezone),
        research_policy_version="synthetic-wp7",
        as_of=datetime.fromisoformat("2026-10-08T12:00:00-07:00"),
    )


def budget():
    return ResearchBudget(
        discovery=DiscoveryBudget(
            max_waves=2,
            max_model_calls=4,
            max_web_search_calls=2,
            max_model_cost_usd=Decimal("0.01"),
        ),
        timeout_seconds=30,
    )


class Source(SyntheticSource):
    def __init__(self):
        self.calls = 0
        self.failure = None
        self.entered = None
        self.release = None
        self.empty = False

    async def collect(self, scope, *, observed_at):
        self.calls += 1
        if self.entered is not None:
            self.entered.set()
            await self.release.wait()
        if self.failure:
            raise self.failure
        if self.empty:
            return RegionalSourceResult(())
        return await super().collect(scope, observed_at=observed_at)


class Semantics(SyntheticSemantics):
    def __init__(self):
        self.calls = []
        self.fail = False

    async def analyze(self, request, *, correction=None):
        self.calls.append(request)
        if self.fail:
            raise SemanticProviderFailure("unavailable", usage=synthetic_usage())
        return await super().analyze(request, correction=correction)


class Discovery(SyntheticDiscovery):
    def __init__(self):
        self.calls = []
        self.fail = False
        self.stop = False

    async def plan(self, context):
        self.calls.append("plan")
        if self.fail:
            raise RuntimeError("sensitive-provider-error-must-not-be-stored")
        if self.stop:
            return DiscoveryProviderResponse(
                value=DiscoveryPlan(
                    gaps=(), tasks=(), should_continue=False, rationale="Synthetic known empty."
                ),
                usage=synthetic_usage(),
            )
        return await super().plan(context)

    async def research(self, context, task, *, max_web_search_calls):
        self.calls.append("research")
        return await super().research(context, task, max_web_search_calls=max_web_search_calls)

    async def verify(self, context, candidates, *, max_web_search_calls):
        self.calls.append("verify")
        return await super().verify(context, candidates, max_web_search_calls=max_web_search_calls)


@pytest.fixture
def worker(database):
    engine, config = database
    command.upgrade(config, "head")
    source, semantics, discovery = Source(), Semantics(), Discovery()
    deps = WorkerDependencies(
        engine=engine,
        registry=SourceRegistry((SourceRegistration(source),)),
        semantic_provider=semantics,
        planner=discovery,
        researcher=discovery,
        verifier=discovery,
    )
    return deps, source, semantics, discovery


def read(deps, key=None):
    with build_session_factory(deps.engine)() as session:
        return read_current_regional_universe(session, (key or scope()).identity)


def counts(deps):
    with build_session_factory(deps.engine)() as session:
        return tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (
                RegionalUniverse,
                RegionalUniverseSnapshot,
                RegionalResearchRun,
            )
        )


async def test_full_worker_persistence_replay_and_read_only_reuse(worker):
    deps, source, semantics, discovery = worker
    result = await run_regional_worker(scope(), deps, budget=budget())
    assert result.status == "success"
    assert source.calls == 1
    assert discovery.calls == ["plan", "research", "verify", "plan"]
    assert len(semantics.calls) == 2
    assert len(semantics.calls[0].opportunities) == len(semantics.calls[1].opportunities) == 1
    assert semantics.calls[0].opportunities[0].title != semantics.calls[1].opportunities[0].title
    first = read(deps)
    assert first.snapshot_id == result.snapshot_id
    assert len(first.universe.opportunities) == 2
    assert all(item.semantics for item in first.universe.opportunities)
    assert first.discovery_summary["usage"]["model_calls"] == 4
    assert len(first.universe.diagnostics) == 4
    assert all(item.estimated_model_cost_usd == 0 for item in first.universe.diagnostics)

    later = ResearchScope.model_validate(
        {
            **scope().model_dump(),
            "as_of": scope().as_of + timedelta(hours=1),
        }
    )
    retry = await run_regional_worker(later, deps, budget=budget())
    assert retry.status == "replayed"
    assert retry.snapshot_id == result.snapshot_id
    assert read(deps) == first  # independent consumer read 1
    assert read(deps) == first  # independent consumer read 2
    assert source.calls == 1 and len(semantics.calls) == 2
    assert len(discovery.calls) == 4
    assert counts(deps) == (1, 1, 1)


async def test_concurrent_same_key_and_distinct_key_isolation(worker):
    deps, source, _, _ = worker
    source.entered, source.release = asyncio.Event(), asyncio.Event()
    first_task = asyncio.create_task(run_regional_worker(scope(), deps, budget=budget()))
    await asyncio.wait_for(source.entered.wait(), 5)
    with build_session_factory(deps.engine)() as session:
        assert session.scalar(select(RegionalResearchRun.status)) == "running"
    second = await run_regional_worker(scope(), deps, budget=budget())
    assert second.status == "busy"
    assert source.calls == 1
    # A second logical weekend remains runnable while the first holds its claim.
    other_source = SyntheticSource()
    other_deps = replace(deps, registry=SourceRegistry((SourceRegistration(other_source),)))
    other = await run_regional_worker(scope(date(2026, 10, 16)), other_deps, budget=budget())
    assert other.status == "success"
    source.release.set()
    first = await first_task
    assert first.status == "success"
    assert (await run_regional_worker(scope(), deps, budget=budget())).status == "replayed"
    assert counts(deps) == (2, 2, 2)


async def test_partial_and_failed_refresh_preserve_last_good(worker):
    deps, source, semantics, discovery = worker
    good = await run_regional_worker(scope(), deps, budget=budget())
    source.failure = RegionalSourceFailure("timeout")
    partial = await run_regional_worker(scope(), deps, budget=budget(), refresh=True)
    assert partial.status == "partial"
    assert read(deps).snapshot_id == good.snapshot_id
    source.failure = None
    semantics.fail = True
    degraded = await run_regional_worker(scope(), deps, budget=budget(), refresh=True)
    assert degraded.status == "partial"
    assert read(deps).snapshot_id == good.snapshot_id
    semantics.fail = False
    discovery.fail = True
    failed = await run_regional_worker(scope(), deps, budget=budget(), refresh=True)
    assert failed.status == "failed"
    assert read(deps).snapshot_id == good.snapshot_id
    with build_session_factory(deps.engine)() as session:
        run = session.get(RegionalResearchRun, failed.run_id)
        assert run.status == "failed" and run.snapshot_id is None
        assert "sensitive-provider-error" not in str(run.diagnostics_payload)
    assert counts(deps) == (1, 3, 4)


async def test_timeout_and_retry_recover_without_successful_snapshot(worker):
    deps, source, _, _ = worker
    source.entered, source.release = asyncio.Event(), asyncio.Event()
    failed = await run_regional_worker(
        scope(),
        deps,
        budget=replace(budget(), timeout_seconds=0.01),
    )
    assert failed.status == "failed" and failed.failure_code == "timeout"
    assert read(deps) is None
    source.entered = None
    assert (await run_regional_worker(scope(), deps, budget=budget())).status == "success"
    assert counts(deps) == (1, 1, 2)


async def test_empty_is_valid_but_no_enabled_sources_is_degraded(worker):
    deps, source, semantics, discovery = worker
    source.empty = True
    discovery.stop = True
    result = await run_regional_worker(scope(), deps, budget=budget())
    assert result.status == "success"
    assert not semantics.calls
    assert read(deps).universe.opportunities == ()
    assert read(deps).universe.sources[0].result_count == 0
    disabled = replace(deps, registry=SourceRegistry(()))
    partial = await run_regional_worker(
        scope(date(2026, 10, 16)),
        disabled,
        budget=budget(),
    )
    assert partial.status == "partial" and partial.failure_code == "not_configured"


async def test_completion_transaction_rollback_preserves_last_good(worker, monkeypatch):
    deps, _, _, _ = worker
    good = await run_regional_worker(scope(), deps, budget=budget())
    import event_radar.shared.worker as module

    original = module.complete_regional_research_run

    def fail_after_flush(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic completion transaction fault")

    monkeypatch.setattr(module, "complete_regional_research_run", fail_after_flush)
    failed = await run_regional_worker(scope(), deps, budget=budget(), refresh=True)
    assert failed.status == "failed"
    assert read(deps).snapshot_id == good.snapshot_id
    assert counts(deps) == (1, 1, 2)


async def test_process_death_releases_claim_and_recovers_committed_attempt(worker):
    deps, _, _, _ = worker
    # Actual process exit without Python context-manager cleanup.
    script = """
import os
from event_radar.db.session import build_engine
from event_radar.db.regional_claim import claim_regional_research
from event_radar.db.regional import begin_regional_research_run
from tests.test_shared_worker_integration import scope
engine = build_engine(os.environ["TEST_DATABASE_URL"])
with claim_regional_research(engine, scope().identity) as claim:
    with claim.session.begin():
        begin_regional_research_run(claim.session, scope())
    os._exit(0)
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    recovered = await run_regional_worker(scope(), deps, budget=budget())
    assert recovered.status == "success"
    with build_session_factory(deps.engine)() as session:
        assert sorted(session.scalars(select(RegionalResearchRun.status))) == ["failed", "success"]
    assert counts(deps) == (1, 1, 2)


async def test_cancellation_records_failure_and_releases_claim(worker):
    deps, source, _, _ = worker
    source.entered, source.release = asyncio.Event(), asyncio.Event()
    task = asyncio.create_task(run_regional_worker(scope(), deps, budget=budget()))
    await asyncio.wait_for(source.entered.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    source.entered = None
    assert (await run_regional_worker(scope(), deps, budget=budget())).status == "success"
    assert counts(deps) == (1, 1, 2)


def test_worker_cli_fresh_process_no_personal_modules_or_network(worker, tmp_path):
    # The full CLI runs with imports, private-file access, and outbound sockets blocked.
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    script = """
import sys, runpy
def guard(event, args):
    if event == "import":
        name = args[0]
        if name.startswith((
            "event_radar.config", "event_radar.main", "event_radar.api",
            "event_radar.services", "event_radar.models.user_context", "openai",
        )):
            raise AssertionError("Personal/API/provider import")
    if event == "open":
        path = str(args[0])
        if any(value in path for value in (".env", ".private-state", "user_context",
                                          "permanent_directions", "temporary_directions")):
            raise AssertionError("Private file access")
    if event == "socket.connect":
        address = args[1]
        if not isinstance(address, tuple) or address[:2] != ("127.0.0.1", 55432):
            raise AssertionError("Non-test network access")
sys.addaudithook(guard)
sys.argv = ["shared_worker", "--region", "sonoma-county-ca", "--weekend", "2026-10-09",
            "--as-of", "2026-10-08T12:00:00-07:00", "--policy-version", "synthetic-wp7",
            "--synthetic"]
runpy.run_module("event_radar.shared_worker", run_name="__main__")
"""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(root / "src"),
        "TEST_DATABASE_URL": os.environ["TEST_DATABASE_URL"],
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [sys.executable, "-B", "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"status": "success"' in result.stdout
    assert list(tmp_path.iterdir()) == []


async def test_verified_duplicate_and_rejected_lead_preserve_inventory(worker):
    from event_radar.models.regional import FactualExclusion
    from event_radar.models.regional_discovery import (
        CandidateVerification,
        DiscoveryResearchResult,
        DiscoveryVerificationResult,
    )
    from event_radar.shared.synthetic import synthetic_candidate

    deps, _, semantics, _ = worker

    class ExcludingSource(SyntheticSource):
        async def collect(self, scope, *, observed_at):
            result = await super().collect(scope, observed_at=observed_at)
            return RegionalSourceResult(
                result.opportunities,
                exclusions=(
                    FactualExclusion(
                        source_id=self.descriptor.source_id,
                        source_record_id="outside",
                        reason="outside_region",
                        duplicate_of=None,
                    ),
                ),
            )

    class Leads(SyntheticDiscovery):
        async def research(self, context, task, *, max_web_search_calls):
            duplicate = synthetic_candidate(context.scope, discovered=False)
            # Independent alternate evidence, avoiding fixture ID collisions.
            payload = duplicate.model_dump()
            payload["evidence"][0]["evidence_id"] = "alternate-duplicate-page"
            duplicate = type(duplicate).model_validate(payload)
            rejected = duplicate.model_copy(update={"candidate_id": "unverified-lead"})
            return DiscoveryProviderResponse(
                value=DiscoveryResearchResult(
                    task_id=task.task_id,
                    candidates=(
                        synthetic_candidate(context.scope, discovered=True),
                        duplicate,
                        rejected,
                    ),
                    source_leads=(),
                ),
                usage=synthetic_usage(),
            )

        async def verify(self, context, candidates, *, max_web_search_calls):
            return DiscoveryProviderResponse(
                value=DiscoveryVerificationResult(
                    decisions=tuple(
                        CandidateVerification(
                            candidate_id=item.candidate_id,
                            verified=item.candidate_id != "unverified-lead",
                            candidate=item if item.candidate_id != "unverified-lead" else None,
                            rejection_code="unverifiable"
                            if item.candidate_id == "unverified-lead"
                            else None,
                            rationale="Independent deterministic verification decision.",
                        )
                        for item in candidates
                    )
                ),
                usage=synthetic_usage(),
            )

    leads = Leads()
    deps = replace(
        deps,
        registry=SourceRegistry((SourceRegistration(ExcludingSource()),)),
        planner=leads,
        researcher=leads,
        verifier=leads,
    )
    result = await run_regional_worker(scope(), deps, budget=budget())
    assert result.status == "success"
    stored = read(deps)
    assert len(stored.universe.opportunities) == 2
    assert {item.reason for item in stored.universe.exclusions} == {
        "outside_region",
        "duplicate_occurrence",
    }
    original_id = semantics.calls[0].opportunities[0].opportunity_id
    original = next(
        item for item in stored.universe.opportunities if item.opportunity_id == original_id
    )
    assert {e.source_id for e in original.evidence} == {"synthetic-source", "adaptive-discovery"}
    assert original.semantics
    assert len(semantics.calls) == 2 and len(semantics.calls[1].opportunities) == 2
    assert stored.discovery_summary["waves"][0]["duplicate_count"] == 1


async def test_lost_database_session_cannot_finalize_without_a_new_claim(worker):
    from sqlalchemy import text

    deps, source, _, _ = worker
    source.entered, source.release = asyncio.Event(), asyncio.Event()
    task = asyncio.create_task(run_regional_worker(scope(), deps, budget=budget()))
    await asyncio.wait_for(source.entered.wait(), 5)
    with deps.engine.begin() as connection:
        # Only terminate the holder of this test's advisory lock, never another DB.
        pid = connection.scalar(
            text(
                "SELECT pid FROM pg_locks WHERE locktype = 'advisory' "
                "AND database = (SELECT oid FROM pg_database WHERE datname = current_database())"
            )
        )
        assert pid is not None
        assert connection.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})
    source.release.set()
    with pytest.raises(RuntimeError, match="claim connection was lost"):
        await task
    assert read(deps) is None
    with build_session_factory(deps.engine)() as session:
        assert session.scalar(select(RegionalResearchRun.status)) == "running"
    source.entered = None
    assert (await run_regional_worker(scope(), deps, budget=budget())).status == "success"
    assert counts(deps) == (1, 1, 2)
