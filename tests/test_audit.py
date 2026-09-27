import json
import subprocess
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from pydantic import HttpUrl

import event_radar.main as main_module
from event_radar.models.ai import AIStageDiagnostics
from event_radar.models.curation import CurationDiagnostics, CurationOutcome
from event_radar.models.event import Event
from event_radar.models.event_analysis import (
    EventDisposition,
    ScrapedEventAnalysis,
    ScrapedEventAnalysisOutcome,
    ScrapedEventJudgment,
    SemanticConfidence,
)
from event_radar.services.audit import AuditWriteResult, write_audit_artifacts
from event_radar.services.event_cards import build_scraped_event_cards
from event_radar.services.event_deduplication import DeduplicationResult
from event_radar.services.event_evaluation import select_event_candidates
from event_radar.services.pipeline import (
    ExternalSourceStatus,
    RecommendationPipelineResult,
    build_event_intelligence_without_ai,
)
from tests.curation_helpers import (
    END,
    PACIFIC_TIME,
    START,
    baseline_weather,
    example_personal_context,
    example_user_context,
    hike_selection,
)


def source_event(title: str, source_id: str, hour: int, categories: set[str]) -> Event:
    start = datetime(2026, 8, 8, hour, tzinfo=PACIFIC_TIME)
    return Event(
        source_name="Fixture",
        source_id=source_id,
        source_url=HttpUrl(f"https://example.com/{source_id}"),
        title=title,
        start_time=start,
        end_time=start + timedelta(hours=2),
        venue="Venue",
        city="Santa Rosa",
        categories=categories,
    )


def fixture_pipeline() -> RecommendationPipelineResult:
    events = [
        source_event("Festival", "festival", 18, {"festival"}),
        source_event("Concert", "concert", 19, {"music"}),
        source_event("Reading", "reading", 14, set()),
    ]
    return RecommendationPipelineResult(
        generated_at=START,
        weekend_start=START,
        weekend_end=END,
        user_context=example_user_context(),
        personal_context=example_personal_context(),
        permanent_directions=[],
        temporary_directions=[],
        sonoma_tourism_events=events[:1],
        happening_sonoma_events=events[1:],
        sonoma_tourism_status=ExternalSourceStatus(success=True, count=1),
        happening_sonoma_status=ExternalSourceStatus(success=True, count=2),
        weather_failure_reason=None,
        deduplication=DeduplicationResult(events=events, duplicates_removed=0),
        valid_events=events,
        factual_rejections={},
        legacy_event_selection=select_event_candidates(events, START, END),
        hike_selection=hike_selection(),
        hike_catalog_size=1,
        baseline_weather=baseline_weather(),
    )


def outcome(event_count: int, hike_count: int) -> CurationOutcome:
    return CurationOutcome(
        curation=None,
        diagnostics=CurationDiagnostics(
            model="test",
            success=False,
            fallback_reason="Disabled.",
            input_event_cards=event_count,
            input_hike_candidates=hike_count,
            retained_event_count=0,
            retained_hike_count=0,
            retained_total_count=0,
            attempts=0,
        ),
    )


def test_new_audit_artifacts_expose_ai_pipeline_and_legacy_is_diagnostic(
    tmp_path: Path,
) -> None:
    pipeline = fixture_pipeline()
    intelligence = build_event_intelligence_without_ai(
        pipeline,
        model="test",
        reason="Disabled.",
    )
    result = write_audit_artifacts(
        pipeline,
        intelligence,
        outcome(
            len(intelligence.context.event_cards),
            len(intelligence.context.hike_candidates),
        ),
        output_root=tmp_path / "audit",
        llm_requested=False,
    )

    assert {path.name for path in result.output_directory.iterdir()} == {
        "00-manifest.json",
        "01-sonoma-tourism.json",
        "02-happening-sonoma.json",
        "03-normalized-deduped.json",
        "04-legacy-deterministic-evaluation.csv",
        "05-legacy-deterministic-evaluation.md",
        "06-scraped-event-analysis.json",
        "07-scraped-event-cards.json",
        "08-web-discovery.json",
        "09-combined-event-universe.json",
        "10-hike-candidates.json",
        "11-recommendation-context.json",
        "12-final-curation.json",
        "13-final-packet.md",
        "personal-context-ai1.md",
        "personal-context-ai2.md",
        "personal-context-ai3.md",
    }
    manifest = json.loads((result.output_directory / "00-manifest.json").read_text())
    assert manifest["sent_to_scraped_event_analysis"] == 3
    assert manifest["personal_experience_context"]["loaded"] is True
    assert manifest["personal_experience_context"]["path"].endswith(
        "personal_experience_preference_context.md"
    )
    assert manifest["source_status"]["sonoma_tourism"] == {
        "success": True,
        "count": 1,
        "failure_reason": None,
    }
    assert manifest["source_status"]["happening_sonoma"]["count"] == 2
    assert manifest["source_status"]["weather"]["success"] is True
    assert manifest["legacy_deterministic_diagnostic"]["production_recall_control"] is False
    assert manifest["scraped_analysis"]["scraped_card_count"] == 3
    assert manifest["combined_event_card_count"] == 3

    deduped = json.loads((result.output_directory / "03-normalized-deduped.json").read_text())
    cards = json.loads((result.output_directory / "07-scraped-event-cards.json").read_text())
    context = json.loads((result.output_directory / "11-recommendation-context.json").read_text())
    assert len(deduped) == 3
    assert len(cards) == 3
    assert context == intelligence.context.model_dump(mode="json")
    assert context["event_cards"] == cards
    assert (result.output_directory / "personal-context-ai1.md").read_text() == (
        intelligence.analysis_request.personal_experience_context
    )
    assert (result.output_directory / "personal-context-ai2.md").read_text() == (
        intelligence.web_request.personal_experience_context
    )
    assert (result.output_directory / "personal-context-ai3.md").read_text() == (
        intelligence.context.personal_experience_context
    )

    legacy = (result.output_directory / "05-legacy-deterministic-evaluation.md").read_text()
    assert "Diagnostic comparison only" in legacy


def test_rejected_scraped_events_remain_visible_in_analysis_audit(tmp_path: Path) -> None:
    pipeline = fixture_pipeline()
    intelligence = build_event_intelligence_without_ai(
        pipeline,
        model="test",
        reason="Disabled.",
    )
    judgments = [
        ScrapedEventJudgment(
            event_id=event.event_id,
            disposition=(EventDisposition.REJECT if index == 2 else EventDisposition.RETAIN),
            experience_summary="Concise semantic review.",
            experience_modes=[],
            interaction_architecture="Unknown.",
            solo_viability="Unknown.",
            active_value="Unknown.",
            distinctiveness="Unknown.",
            social_opportunity="Unknown.",
            friction_summary="Unknown.",
            schedule_observation="No known conflict.",
            uncertainties=[],
            reason_for_disposition="Audit routing fixture.",
            confidence=SemanticConfidence.MODERATE,
        )
        for index, event in enumerate(intelligence.analysis_request.events)
    ]
    analysis = ScrapedEventAnalysis(events=judgments, experience_groups=[])
    analysis_outcome = ScrapedEventAnalysisOutcome(
        analysis=analysis,
        diagnostics=AIStageDiagnostics(
            stage="scraped_event_analysis",
            model="test",
            success=True,
            input_count=3,
            result_count=3,
            attempts=1,
        ),
    )
    cards = build_scraped_event_cards(intelligence.analysis_request, analysis)
    intelligence = replace(
        intelligence,
        analysis_outcome=analysis_outcome,
        scraped_event_cards=cards,
        combined_event_cards=cards,
    )

    result = write_audit_artifacts(
        pipeline,
        intelligence,
        outcome(len(cards), len(intelligence.context.hike_candidates)),
        output_root=tmp_path / "audit",
        llm_requested=True,
    )

    audited = json.loads((result.output_directory / "06-scraped-event-analysis.json").read_text())
    assert audited["analysis"]["events"][2]["disposition"] == "reject"
    card_ids = {
        card["candidate_id"]
        for card in json.loads(
            (result.output_directory / "07-scraped-event-cards.json").read_text()
        )
    }
    assert intelligence.analysis_request.events[2].event_id not in card_ids


@pytest.mark.asyncio
async def test_audit_execution_never_enters_telegram_or_state_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pipeline = fixture_pipeline()
    intelligence = build_event_intelligence_without_ai(
        pipeline,
        model="test",
        reason="Disabled.",
    )
    wrote: list[bool] = []

    async def build_pipeline() -> RecommendationPipelineResult:
        return pipeline

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Audit entered Telegram/state mutation.")

    def write(
        *args: object,
        **kwargs: object,
    ) -> AuditWriteResult:
        wrote.append(True)
        return AuditWriteResult(tmp_path / "audit", 0, 0)

    monkeypatch.setattr(main_module, "_build_current_pipeline", build_pipeline)
    monkeypatch.setattr(
        main_module,
        "build_event_intelligence_without_ai",
        lambda *args, **kwargs: intelligence,
    )
    monkeypatch.setattr(main_module, "write_audit_artifacts", write)
    monkeypatch.setattr(main_module, "_print_pipeline_diagnostics", lambda *args: None)
    monkeypatch.setattr(main_module, "read_directions", forbidden)
    monkeypatch.setattr(main_module, "deliver_weekend_digest", forbidden)
    monkeypatch.setattr(main_module, "load_offset", forbidden)
    monkeypatch.setattr(main_module, "save_offset", forbidden)
    monkeypatch.setattr(main_module, "save_direction", forbidden)
    monkeypatch.setattr(main_module, "clear_temporary_directions", forbidden)

    await main_module.run_audit(run_llm=False)

    assert wrote == [True]


@pytest.mark.asyncio
async def test_execute_preserves_audit_and_normal_production_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def audit(*, run_llm: bool) -> None:
        calls.append(f"audit:{run_llm}")

    async def read() -> None:
        calls.append("read")

    async def run() -> None:
        calls.append("run")

    monkeypatch.setattr(main_module, "run_audit", audit)
    monkeypatch.setattr(main_module, "read_directions", read)
    monkeypatch.setattr(main_module, "run", run)
    await main_module.execute(audit=True, run_llm=False)
    await main_module.execute()

    assert calls == ["audit:False", "read", "run"]


def test_audit_directory_is_gitignored() -> None:
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", "audit/2026-08-07/00-manifest.json"],
        check=False,
    )
    assert result.returncode == 0


def test_audit_manifest_records_degraded_source_and_weather_status(tmp_path: Path) -> None:
    pipeline = replace(
        fixture_pipeline(),
        happening_sonoma_events=[],
        happening_sonoma_status=ExternalSourceStatus(
            success=False,
            count=0,
            failure_reason=(
                "Happening in Sonoma County returned invalid JSON after 3 attempt(s) "
                "(status=200, content_type='text/html')."
            ),
        ),
        baseline_weather=None,
        weather_failure_reason="Open-Meteo request timed out.",
    )
    intelligence = build_event_intelligence_without_ai(
        pipeline,
        model="test",
        reason="Disabled.",
    )
    result = write_audit_artifacts(
        pipeline,
        intelligence,
        outcome(
            len(intelligence.context.event_cards),
            len(intelligence.context.hike_candidates),
        ),
        output_root=tmp_path / "audit",
        llm_requested=False,
    )

    manifest = json.loads((result.output_directory / "00-manifest.json").read_text())
    happening = manifest["source_status"]["happening_sonoma"]
    assert happening["success"] is False
    assert happening["count"] == 0
    assert "invalid JSON after 3 attempt(s)" in happening["failure_reason"]
    assert manifest["source_status"]["weather"] == {
        "success": False,
        "failure_reason": "Open-Meteo request timed out.",
    }
