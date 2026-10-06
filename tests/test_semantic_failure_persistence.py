"""Safe semantic failure evidence against disposable PostgreSQL and fake providers."""

from dataclasses import replace
from decimal import Decimal

import pytest
from sqlalchemy import select

from event_radar.db.models import RegionalResearchRun, RegionalUniverseSnapshot
from event_radar.db.session import build_session_factory
from event_radar.shared.collection import RegionalSourceResult, SourceRegistration, SourceRegistry
from event_radar.shared.discovery import materialize_discovered_event
from event_radar.shared.semantic_analysis import SemanticProviderFailure
from event_radar.shared.synthetic import SyntheticSource, synthetic_candidate, synthetic_usage
from event_radar.shared.worker import run_regional_worker
from tests.test_regional_semantic_analysis import FakeSemanticProvider
from tests.test_shared_worker_integration import budget, counts, read, scope
from tests.test_shared_worker_integration import worker as worker

SENTINEL = "RAW_RESPONSE_AND_CREDENTIAL_SENTINEL"


@pytest.mark.parametrize("category", ["provider_transport", "sdk_parse"])
async def test_expected_provider_failures_persist_partial_evidence_and_protect_good(
    worker, category
):
    deps, _, _, _ = worker
    good = await run_regional_worker(scope(), deps, budget=budget())

    class Expected:
        model_id = "offline"

        async def analyze(self, request, *, correction=None):
            raise SemanticProviderFailure(
                "invalid_response" if category == "sdk_parse" else "unavailable",
                category=category,
                usage=synthetic_usage(),
                latency_seconds=0.2,
            ) from RuntimeError(SENTINEL)

    partial = await run_regional_worker(
        scope(),
        replace(deps, semantic_provider=Expected()),
        budget=budget(),
        refresh=True,
    )
    assert partial.status == "partial"
    assert read(deps).snapshot_id == good.snapshot_id
    with build_session_factory(deps.engine)() as session:
        run = session.get(RegionalResearchRun, partial.run_id)
        stages = run.diagnostics_payload["stages"]
        semantic = next(item for item in stages if item["stage"] == "semantic_analysis")
        assert semantic["failure_category"] == category
        assert semantic["provider_calls"] == semantic["attempts"] == 1
        assert semantic["usage_complete"] is True
        assert semantic["latency_seconds"] == 0.2
        assert SENTINEL not in str(stages)
        assert (
            session.get(RegionalUniverseSnapshot, partial.snapshot_id).quality_status == "partial"
        )


async def test_unexpected_second_batch_failure_preserves_telemetry_and_last_good(worker):
    deps, _, _, _ = worker

    class TwoSource(SyntheticSource):
        async def collect(self, research_scope, *, observed_at):
            return RegionalSourceResult(
                tuple(
                    materialize_discovered_event(
                        research_scope,
                        synthetic_candidate(research_scope, discovered=discovered),
                        observed_at=observed_at,
                        source_id=self.descriptor.source_id,
                    )
                    for discovered in (False, True)
                )
            )

    deps = replace(deps, registry=SourceRegistry((SourceRegistration(TwoSource()),)))
    good = await run_regional_worker(scope(), deps, budget=budget())

    class LocalFailure(FakeSemanticProvider):
        async def analyze(self, request, *, correction=None):
            if self.requests:
                raise RuntimeError(SENTINEL)
            return await super().analyze(request, correction=correction)

    failed = await run_regional_worker(
        scope(),
        replace(deps, semantic_provider=LocalFailure()),
        budget=replace(budget(), semantic_batch_size=1),
        refresh=True,
    )
    assert failed.status == "failed" and failed.failure_code == "invalid_response"
    assert failed.snapshot_id is None
    assert read(deps).snapshot_id == good.snapshot_id
    assert counts(deps) == (1, 1, 2)
    with build_session_factory(deps.engine)() as session:
        run = session.get(RegionalResearchRun, failed.run_id)
        failure = run.diagnostics_payload["stages"][-1]
        assert failure["stage"] == "semantic_analysis" and failure["status"] == "failed"
        assert failure["failure_category"] == "local_invariant"
        assert failure["provider_calls"] == 2
        assert failure["attempts"] == 1 and failure["attempts_complete"] is False
        assert failure["total_tokens"] == 15
        assert Decimal(failure["estimated_model_cost_usd"]) == Decimal("0.002")
        assert failure["usage_complete"] is False
        assert SENTINEL not in str(run.diagnostics_payload)
        assert run.snapshot_id is None
        assert len(session.scalars(select(RegionalUniverseSnapshot)).all()) == 1


async def test_unexpected_semantic_validation_failure_has_no_snapshot(worker):
    from event_radar.models.regional_semantics import RegionalSemanticAnalysis

    deps, _, _, _ = worker

    class Invalid:
        model_id = "offline"

        async def analyze(self, request, *, correction=None):
            RegionalSemanticAnalysis.model_validate({"opportunities": SENTINEL})

    failed = await run_regional_worker(
        scope(),
        replace(deps, semantic_provider=Invalid()),
        budget=budget(),
    )
    assert failed.status == "failed" and failed.snapshot_id is None
    assert read(deps) is None and counts(deps) == (1, 0, 1)
    with build_session_factory(deps.engine)() as session:
        run = session.get(RegionalResearchRun, failed.run_id)
        failure = run.diagnostics_payload["stages"][-1]
        assert failure["failure_category"] == "local_validation"
        assert failure["failure_code"] == "invalid_response"
        assert SENTINEL not in str(run.diagnostics_payload)


async def test_semantic_timeout_is_distinguished_from_manual_cancellation(worker):
    import asyncio

    deps, _, _, _ = worker

    class Slow:
        model_id = "offline"

        async def analyze(self, request, *, correction=None):
            await asyncio.Event().wait()

    failed = await run_regional_worker(
        scope(),
        replace(deps, semantic_provider=Slow()),
        budget=replace(budget(), timeout_seconds=0.02),
    )
    assert failed.status == "failed" and failed.failure_code == "timeout"
    with build_session_factory(deps.engine)() as session:
        failure = session.get(RegionalResearchRun, failed.run_id).diagnostics_payload["stages"][-1]
        assert failure["stage"] == "semantic_analysis"
        assert failure["failure_category"] == "timeout"
        assert failure["provider_calls"] == 1 and failure["attempts_complete"] is False
        assert failure["total_tokens"] is None
