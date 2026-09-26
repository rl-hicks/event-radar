from datetime import datetime, timedelta
from typing import cast

import pytest
from pydantic import HttpUrl

import event_radar.services.pipeline as pipeline_module
from event_radar.collectors.happening_sonoma import (
    HappeningSonomaCollector,
    HappeningSonomaCollectorError,
)
from event_radar.collectors.sonoma_county import (
    SonomaCountyCollector,
    SonomaCountyCollectorError,
)
from event_radar.models.ai import AIStageDiagnostics
from event_radar.models.curation import CurationDiagnostics, CurationOutcome
from event_radar.models.event import Event
from event_radar.models.event_analysis import SemanticConfidence
from event_radar.models.web_discovery import (
    DiscoveredEvent,
    WebDiscoveryOutcome,
    WebDiscoveryRequest,
    WebDiscoveryResult,
)
from event_radar.services.curation_rendering import render_chatgpt_packet
from event_radar.services.event_deduplication import DeduplicationResult
from event_radar.services.event_evaluation import select_event_candidates
from event_radar.services.pipeline import (
    ExternalSourceStatus,
    RecommendationPipelineResult,
    build_event_intelligence,
    collect_event_sources,
)
from tests.curation_helpers import (
    END,
    PACIFIC_TIME,
    START,
    example_user_context,
    hike_selection,
)


def _event(title: str = "Source Event") -> Event:
    start = datetime(2026, 8, 8, 18, tzinfo=PACIFIC_TIME)
    return Event(
        source_name="Fixture",
        source_id="source-event",
        source_url=HttpUrl("https://example.com/source-event"),
        title=title,
        start_time=start,
        end_time=start + timedelta(hours=2),
        venue="Town Square",
        city="Santa Rosa",
        categories={"community"},
    )


class _Collector:
    def __init__(self, events: list[Event] | None = None, error: Exception | None = None) -> None:
        self.events = events or []
        self.error = error
        self.calls = 0

    async def collect(self, start: datetime, end: datetime) -> list[Event]:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.events


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sonoma_error", "happening_error", "sonoma_success", "happening_success"),
    [
        (None, None, True, True),
        (None, HappeningSonomaCollectorError("invalid JSON"), True, False),
        (SonomaCountyCollectorError("upstream 503"), None, False, True),
        (
            SonomaCountyCollectorError("upstream 503"),
            HappeningSonomaCollectorError("invalid JSON"),
            False,
            False,
        ),
    ],
)
async def test_collect_event_sources_degrades_each_known_provider_independently(
    sonoma_error: Exception | None,
    happening_error: Exception | None,
    sonoma_success: bool,
    happening_success: bool,
) -> None:
    sonoma = _Collector(events=[_event("Sonoma")], error=sonoma_error)
    happening = _Collector(events=[_event("Happening")], error=happening_error)

    sonoma_result, happening_result = await collect_event_sources(
        cast(SonomaCountyCollector, sonoma),
        cast(HappeningSonomaCollector, happening),
        start=START,
        end=END,
    )

    assert sonoma_result.status.success is sonoma_success
    assert happening_result.status.success is happening_success
    assert sonoma_result.status.count == (1 if sonoma_success else 0)
    assert happening_result.status.count == (1 if happening_success else 0)
    assert bool(sonoma_result.status.failure_reason) is (not sonoma_success)
    assert bool(happening_result.status.failure_reason) is (not happening_success)
    assert sonoma.calls == happening.calls == 1


@pytest.mark.asyncio
async def test_collect_event_sources_does_not_mask_programming_errors() -> None:
    sonoma = _Collector(error=RuntimeError("internal invariant failed"))
    happening = _Collector(events=[])

    with pytest.raises(RuntimeError, match="internal invariant failed"):
        await collect_event_sources(
            cast(SonomaCountyCollector, sonoma),
            cast(HappeningSonomaCollector, happening),
            start=START,
            end=END,
        )


def _empty_failed_pipeline() -> RecommendationPipelineResult:
    empty_selection = select_event_candidates([], START, END)
    return RecommendationPipelineResult(
        generated_at=START,
        weekend_start=START,
        weekend_end=END,
        user_context=example_user_context(),
        permanent_directions=[],
        temporary_directions=[],
        sonoma_tourism_events=[],
        happening_sonoma_events=[],
        sonoma_tourism_status=ExternalSourceStatus(
            success=False,
            count=0,
            failure_reason="Sonoma upstream 503",
        ),
        happening_sonoma_status=ExternalSourceStatus(
            success=False,
            count=0,
            failure_reason="Happening invalid JSON",
        ),
        weather_failure_reason="Open-Meteo timed out",
        deduplication=DeduplicationResult(events=[], duplicates_removed=0),
        valid_events=[],
        factual_rejections={},
        legacy_event_selection=empty_selection,
        hike_selection=hike_selection(),
        hike_catalog_size=1,
        baseline_weather=None,
    )


def _discovered_event() -> DiscoveredEvent:
    start = datetime(2026, 8, 8, 19, tzinfo=PACIFIC_TIME)
    return DiscoveredEvent(
        discovery_id="web_discovery",
        title="Verified Web Event",
        source_url="https://example.org/verified-event",
        source_name="Official organizer",
        start_time=start,
        end_time=start + timedelta(hours=2),
        venue="Community Hall",
        city="Santa Rosa",
        description_evidence="Official organizer lists the event for Saturday evening.",
        why_it_may_fit="A public local gathering.",
        experience_summary="A verified community gathering.",
        experience_modes=["community"],
        interaction_architecture="Shared public space.",
        solo_viability="Normal to attend solo.",
        active_value="Light activity.",
        distinctiveness="One-time local event.",
        social_opportunity="Plausible public interaction.",
        friction_summary="Local.",
        schedule_observation="No known conflict.",
        uncertainties=["Attendance unknown."],
        verification_confidence=SemanticConfidence.HIGH,
        source_confidence=SemanticConfidence.HIGH,
    )


@pytest.mark.asyncio
async def test_zero_scraped_inventory_skips_ai1_but_runs_web_and_builds_web_hike_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    web_called = False
    discovery = _discovered_event()

    async def fake_discovery(service: object, request: WebDiscoveryRequest) -> WebDiscoveryOutcome:
        nonlocal web_called
        web_called = True
        assert request.existing_events == []
        return WebDiscoveryOutcome(
            result=WebDiscoveryResult(discoveries=[discovery]),
            valid_discoveries=[discovery],
            duplicates_removed=0,
            diagnostics=AIStageDiagnostics(
                stage="web_event_discovery",
                model="web-test",
                success=True,
                input_count=0,
                result_count=1,
                attempts=1,
                tool_calls=1,
            ),
        )

    monkeypatch.setattr(pipeline_module, "discover_events_with_fallback", fake_discovery)

    class AnalysisService:
        model = "analysis-test"

        async def analyze(self, request: object) -> object:
            raise AssertionError("AI #1 must not run for an empty scraped inventory.")

    class WebService:
        model = "web-test"

    result = await build_event_intelligence(
        _empty_failed_pipeline(),
        analysis_service=cast(object, AnalysisService()),  # type: ignore[arg-type]
        web_service=cast(object, WebService()),  # type: ignore[arg-type]
    )

    assert web_called is True
    assert result.analysis_outcome.analysis is None
    assert result.analysis_outcome.diagnostics.attempts == 0
    assert result.analysis_outcome.diagnostics.input_count == 0
    assert len(result.web_event_cards) == 1
    assert result.context.event_cards == result.web_event_cards
    assert len(result.context.hike_candidates) == 1
    assert any(
        "Both fixed event feeds were unavailable" in note
        for note in result.context.event_pipeline_notes
    )
    assert any("Weather unavailable" in note for note in result.context.event_pipeline_notes)

    outcome = CurationOutcome(
        curation=None,
        diagnostics=CurationDiagnostics(
            model="curation-test",
            success=False,
            fallback_reason="not invoked in unit test",
            input_event_cards=1,
            input_hike_candidates=1,
            retained_options=0,
            attempts=0,
        ),
    )
    packet = render_chatgpt_packet(result.context, outcome)
    assert "## Event research status" in packet
    assert "Both fixed event feeds were unavailable" in packet
    assert "Weather unavailable" in packet
