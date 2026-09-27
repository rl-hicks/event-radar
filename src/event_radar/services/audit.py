import csv
import json
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from event_radar.models.curation import CurationOutcome
from event_radar.models.event import Event
from event_radar.models.event_analysis import EventDisposition
from event_radar.models.recommendation import EventEvaluation
from event_radar.recommendation_config import DEFAULT_RECOMMENDATION_CONFIG
from event_radar.services.curation_rendering import format_event_time_range, render_chatgpt_packet
from event_radar.services.pipeline import EventIntelligenceResult, RecommendationPipelineResult
from event_radar.services.recommendation_context import event_candidate_id


class LegacyEvaluationRecord(BaseModel):
    event_id: str
    title: str
    local_date_time: str
    city: str
    categories: list[str]
    deterministic_score: int
    reasons: list[str]
    hard_excluded: bool
    hard_exclusion_reasons: list[str]
    legacy_qualified: bool
    legacy_selected: bool
    legacy_rank: int | None
    legacy_nonselection_reason: str | None


@dataclass(frozen=True)
class AuditWriteResult:
    output_directory: Path
    retained_event_count: int
    retained_hike_count: int

    @property
    def retained_option_count(self) -> int:
        return self.retained_event_count + self.retained_hike_count


def write_audit_artifacts(
    pipeline: RecommendationPipelineResult,
    intelligence: EventIntelligenceResult,
    outcome: CurationOutcome,
    *,
    output_root: Path = Path("audit"),
    llm_requested: bool,
) -> AuditWriteResult:
    timezone = ZoneInfo(pipeline.user_context.base_location.timezone)
    friday = (pipeline.weekend_end.astimezone(timezone) - timedelta(days=3)).date()
    directory = output_root / friday.isoformat()
    directory.mkdir(parents=True, exist_ok=True)
    _remove_obsolete_audit_artifacts(directory)

    legacy = _legacy_records(pipeline, timezone)
    dispositions = {value.value: 0 for value in EventDisposition}
    groups = 0
    if intelligence.analysis_outcome.analysis is not None:
        for judgment in intelligence.analysis_outcome.analysis.events:
            dispositions[judgment.disposition.value] += 1
        groups = len(intelligence.analysis_outcome.analysis.experience_groups)

    diagnostics = [
        intelligence.analysis_outcome.diagnostics,
        intelligence.web_outcome.diagnostics,
    ]
    manifest = {
        "audit_timestamp": pipeline.generated_at.isoformat(),
        "weekend_window": {
            "start": pipeline.weekend_start.isoformat(),
            "end": pipeline.weekend_end.isoformat(),
        },
        "application_timezone": timezone.key,
        "personal_experience_context": {
            "path": str(pipeline.personal_context.source_path),
            "loaded": True,
            "ai1_projection_characters": len(
                intelligence.analysis_request.personal_experience_context
            ),
            "ai2_projection_characters": len(intelligence.web_request.personal_experience_context),
            "ai3_projection_characters": len(intelligence.context.personal_experience_context),
        },
        "collector_counts": {
            "sonoma_tourism": len(pipeline.sonoma_tourism_events),
            "happening_sonoma": len(pipeline.happening_sonoma_events),
        },
        "source_status": {
            "sonoma_tourism": {
                "success": pipeline.sonoma_tourism_status.success,
                "count": pipeline.sonoma_tourism_status.count,
                "failure_reason": pipeline.sonoma_tourism_status.failure_reason,
            },
            "happening_sonoma": {
                "success": pipeline.happening_sonoma_status.success,
                "count": pipeline.happening_sonoma_status.count,
                "failure_reason": pipeline.happening_sonoma_status.failure_reason,
            },
            "weather": {
                "success": pipeline.baseline_weather is not None,
                "failure_reason": pipeline.weather_failure_reason,
            },
        },
        "duplicates_removed": pipeline.deduplication.duplicates_removed,
        "deduplicated_count": len(pipeline.deduplication.events),
        "factual_valid_count": len(pipeline.valid_events),
        "factual_rejected_count": len(pipeline.factual_rejections),
        "sent_to_scraped_event_analysis": len(intelligence.analysis_request.events),
        "legacy_deterministic_diagnostic": {
            "production_recall_control": False,
            "eligible_count": pipeline.legacy_event_selection.eligible_count,
            "hard_excluded_count": pipeline.legacy_event_selection.excluded_count,
            "legacy_selected_count": len(pipeline.legacy_event_selection.candidates),
            "configured_minimum_score": DEFAULT_RECOMMENDATION_CONFIG.minimum_score,
            "configured_candidate_cap": DEFAULT_RECOMMENDATION_CONFIG.maximum_candidates,
        },
        "scraped_analysis": {
            "requested": llm_requested,
            "ran": intelligence.analysis_outcome.diagnostics.attempts > 0,
            "success": intelligence.analysis_outcome.diagnostics.success,
            "dispositions": dispositions,
            "experience_group_count": groups,
            "scraped_card_count": len(intelligence.scraped_event_cards),
            "diagnostics": intelligence.analysis_outcome.diagnostics.model_dump(mode="json"),
        },
        "web_discovery": {
            "requested": llm_requested,
            "ran": intelligence.web_outcome.diagnostics.attempts > 0,
            "success": intelligence.web_outcome.diagnostics.success,
            "returned_count": (
                len(intelligence.web_outcome.result.discoveries)
                if intelligence.web_outcome.result is not None
                else 0
            ),
            "valid_count": len(intelligence.web_outcome.valid_discoveries),
            "duplicates_removed": intelligence.web_outcome.duplicates_removed,
            "diagnostics": intelligence.web_outcome.diagnostics.model_dump(mode="json"),
        },
        "combined_event_card_count": len(intelligence.combined_event_cards),
        "hike_candidate_count": len(intelligence.context.hike_candidates),
        "final_curation": {
            "ran": outcome.diagnostics.attempts > 0,
            "success": outcome.diagnostics.success,
            "retained_event_count": (
                len(outcome.curation.event_options) if outcome.curation is not None else 0
            ),
            "retained_hike_count": (
                len(outcome.curation.hike_options) if outcome.curation is not None else 0
            ),
            "retained_total_count": (
                len(outcome.curation.event_options) + len(outcome.curation.hike_options)
                if outcome.curation is not None
                else 0
            ),
            "diagnostics": outcome.diagnostics.model_dump(mode="json"),
        },
        "aggregate_ai_tokens": sum(item.total_tokens or 0 for item in diagnostics)
        + (outcome.diagnostics.total_tokens or 0),
        "aggregate_ai_latency_seconds": sum(item.latency_seconds or 0 for item in diagnostics)
        + (outcome.diagnostics.latency_seconds or 0),
    }

    _write_json(directory / "00-manifest.json", manifest)
    _write_json(
        directory / "01-sonoma-tourism.json",
        [_event_record(event, timezone) for event in pipeline.sonoma_tourism_events],
    )
    _write_json(
        directory / "02-happening-sonoma.json",
        [_event_record(event, timezone) for event in pipeline.happening_sonoma_events],
    )
    _write_json(
        directory / "03-normalized-deduped.json",
        [_event_record(event, timezone) for event in pipeline.deduplication.events],
    )
    _write_legacy_csv(directory / "04-legacy-deterministic-evaluation.csv", legacy)
    (directory / "05-legacy-deterministic-evaluation.md").write_text(
        _legacy_markdown(legacy),
        encoding="utf-8",
    )
    _write_json(
        directory / "06-scraped-event-analysis.json",
        intelligence.analysis_outcome.model_dump(mode="json"),
    )
    _write_json(
        directory / "07-scraped-event-cards.json",
        [card.model_dump(mode="json") for card in intelligence.scraped_event_cards],
    )
    _write_json(
        directory / "08-web-discovery.json",
        intelligence.web_outcome.model_dump(mode="json"),
    )
    _write_json(
        directory / "09-combined-event-universe.json",
        [card.model_dump(mode="json") for card in intelligence.combined_event_cards],
    )
    _write_json(
        directory / "10-hike-candidates.json",
        [candidate.model_dump(mode="json") for candidate in intelligence.context.hike_candidates],
    )
    (directory / "11-recommendation-context.json").write_text(
        intelligence.context.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    (directory / "personal-context-ai1.md").write_text(
        intelligence.analysis_request.personal_experience_context,
        encoding="utf-8",
    )
    (directory / "personal-context-ai2.md").write_text(
        intelligence.web_request.personal_experience_context,
        encoding="utf-8",
    )
    (directory / "personal-context-ai3.md").write_text(
        intelligence.context.personal_experience_context,
        encoding="utf-8",
    )
    _write_json(directory / "12-final-curation.json", outcome.model_dump(mode="json"))
    (directory / "13-final-packet.md").write_text(
        render_chatgpt_packet(intelligence.context, outcome),
        encoding="utf-8",
    )
    return AuditWriteResult(
        output_directory=directory,
        retained_event_count=(
            len(outcome.curation.event_options) if outcome.curation is not None else 0
        ),
        retained_hike_count=(
            len(outcome.curation.hike_options) if outcome.curation is not None else 0
        ),
    )


def _legacy_records(
    pipeline: RecommendationPipelineResult,
    timezone: ZoneInfo,
) -> list[LegacyEvaluationRecord]:
    ranks = {
        event_candidate_id(value.event): rank
        for rank, value in enumerate(pipeline.legacy_event_selection.candidates, start=1)
    }
    records = [
        _legacy_record(evaluation, ranks=ranks, timezone=timezone)
        for evaluation in pipeline.legacy_event_selection.evaluations
    ]
    return sorted(
        records,
        key=lambda value: (
            0 if value.legacy_selected else 1 if not value.hard_excluded else 2,
            value.legacy_rank or 9999,
            -value.deterministic_score,
            value.title.casefold(),
        ),
    )


def _legacy_record(
    evaluation: EventEvaluation,
    *,
    ranks: dict[str, int],
    timezone: ZoneInfo,
) -> LegacyEvaluationRecord:
    identifier = event_candidate_id(evaluation.event)
    rank = ranks.get(identifier)
    qualified = (
        evaluation.eligible and evaluation.score >= DEFAULT_RECOMMENDATION_CONFIG.minimum_score
    )
    reason: str | None = None
    if rank is None:
        if not evaluation.eligible:
            reason = "hard excluded: " + "; ".join(evaluation.exclusion_reasons)
        elif not qualified:
            reason = "below legacy minimum relevance score"
        else:
            reason = "outside legacy semantic candidate cap/diversity selection"
    return LegacyEvaluationRecord(
        event_id=identifier,
        title=evaluation.event.title,
        local_date_time=format_event_time_range(
            evaluation.event.start_time,
            evaluation.event.end_time,
            timezone,
        ),
        city=evaluation.event.city,
        categories=sorted(evaluation.event.categories),
        deterministic_score=evaluation.score,
        reasons=evaluation.reasons,
        hard_excluded=not evaluation.eligible,
        hard_exclusion_reasons=evaluation.exclusion_reasons,
        legacy_qualified=qualified,
        legacy_selected=rank is not None,
        legacy_rank=rank,
        legacy_nonselection_reason=reason,
    )


def _legacy_markdown(records: list[LegacyEvaluationRecord]) -> str:
    lines = [
        "# Legacy Deterministic Event Evaluation",
        "",
        "**Diagnostic comparison only. This scorer does not control production event recall.**",
        "",
    ]
    for record in records:
        lines.extend(
            [
                f"## {record.title}",
                "",
                f"- Event ID: `{record.event_id}`",
                f"- Local time: {record.local_date_time}",
                f"- Score: {record.deterministic_score}",
                f"- Reasons: {'; '.join(record.reasons) or 'none'}",
                f"- Hard excluded: {'yes' if record.hard_excluded else 'no'}",
                f"- Legacy selected: {'yes' if record.legacy_selected else 'no'}",
                f"- Legacy rank: {record.legacy_rank or 'none'}",
                f"- Legacy non-selection: {record.legacy_nonselection_reason or 'not applicable'}",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def _write_legacy_csv(path: Path, records: list[LegacyEvaluationRecord]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(LegacyEvaluationRecord.model_fields))
        writer.writeheader()
        for record in records:
            row = record.model_dump(mode="json")
            for field in ("categories", "reasons", "hard_exclusion_reasons"):
                row[field] = json.dumps(row[field], ensure_ascii=False)
            writer.writerow(row)


def _event_record(event: Event, timezone: ZoneInfo) -> dict[str, Any]:
    record = event.model_dump(mode="json")
    record.update(
        {
            "event_id": event_candidate_id(event),
            "local_start_time": event.start_time.astimezone(timezone).isoformat(),
            "local_end_time": (
                event.end_time.astimezone(timezone).isoformat()
                if event.end_time is not None
                else None
            ),
            "local_rendered_time": format_event_time_range(
                event.start_time, event.end_time, timezone
            ),
        }
    )
    return record


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _remove_obsolete_audit_artifacts(directory: Path) -> None:
    """Remove files from the superseded deterministic-selection audit layout."""
    for filename in (
        "04-deterministic-evaluation.csv",
        "05-deterministic-evaluation.md",
        "06-selected-event-candidates.json",
        "07-hike-candidates.json",
        "08-recommendation-context.json",
        "09-llm-curation.json",
        "10-final-packet.md",
    ):
        (directory / filename).unlink(missing_ok=True)
