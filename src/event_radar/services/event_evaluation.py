import re
import unicodedata
from collections.abc import Iterable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from event_radar.models.event import Event
from event_radar.models.recommendation import CandidateSelection, EventEvaluation
from event_radar.recommendation_config import (
    DEFAULT_RECOMMENDATION_CONFIG,
    RecommendationScoringConfig,
    ScoringSignal,
)

PACIFIC_TIME = ZoneInfo("America/Los_Angeles")
_NON_WORD_PATTERN = re.compile(r"[^\w+]+", re.UNICODE)


def evaluate_event(
    event: Event,
    start: datetime,
    end: datetime,
    config: RecommendationScoringConfig = DEFAULT_RECOMMENDATION_CONFIG,
) -> EventEvaluation:
    """Apply conservative eligibility checks and modest structured scoring."""
    _validate_window(start, end)
    exclusion_reasons = _exclusion_reasons(event, start, end, config)
    if exclusion_reasons:
        return EventEvaluation(
            event=event,
            eligible=False,
            score=0,
            exclusion_reasons=exclusion_reasons,
        )

    category_texts = tuple(_normalize_text(category) for category in sorted(event.categories))
    title_text = _normalize_text(event.title)
    description_text = _normalize_text(event.description or "")

    semantic_matches: list[tuple[ScoringSignal, str, int]] = []
    semantic_non_description_score = 0
    description_only_semantic_score = 0

    for signal in config.scoring_signals:
        match = _strongest_signal_match(
            signal,
            category_texts=category_texts,
            title_text=title_text,
            description_text=description_text,
        )
        if match is None:
            continue

        evidence, weight = match
        semantic_matches.append((signal, evidence, weight))
        if evidence == "description":
            description_only_semantic_score += weight
        else:
            semantic_non_description_score += weight

    capped_description_score = min(
        description_only_semantic_score,
        config.description_signal_score_cap,
    )
    score = semantic_non_description_score + capped_description_score
    reasons: list[str] = []
    matched_activity_types: list[tuple[int, str]] = []
    remaining_description_score = capped_description_score

    for signal, evidence, weight in semantic_matches:
        awarded_weight = weight
        if evidence == "description":
            awarded_weight = min(weight, remaining_description_score)
            remaining_description_score -= awarded_weight
        if awarded_weight <= 0:
            continue

        reasons.append(f"{signal.reason} [{evidence}]")
        matched_activity_types.append((awarded_weight, signal.activity_type))

    if description_only_semantic_score > capped_description_score:
        reasons.append(f"description-only semantic score capped at {capped_description_score}")

    text = _event_text(event)

    if (
        event.description
        and len(event.description.strip()) >= config.description_substance_minimum_characters
    ):
        score += config.description_substance_boost
        reasons.append("substantive event description")

    local_start = event.start_time.astimezone(PACIFIC_TIME)
    if local_start.hour >= 17:
        score += config.evening_event_boost
        reasons.append("evening timing")

    if event.end_time is not None:
        duration = event.end_time - event.start_time
        if timedelta(hours=1) <= duration <= timedelta(hours=6):
            score += config.practical_duration_boost
            reasons.append("practical event duration")

    if event.is_free():
        score += config.free_event_boost
        reasons.append("free admission")

    if _contains_any(text, config.child_focused_terms):
        score += config.child_focused_penalty
        reasons.append("primarily family or child focused")

    if _contains_any(text, config.administrative_terms):
        score += config.administrative_event_penalty
        reasons.append("routine administrative purpose")

    if _contains_any(text, config.generic_recurring_terms):
        score += config.generic_recurring_penalty
        reasons.append("generic recurring listing")

    activity_type = (
        max(matched_activity_types, key=lambda matched: matched[0])[1]
        if matched_activity_types
        else "other"
    )
    return EventEvaluation(
        event=event,
        eligible=True,
        score=score,
        reasons=reasons,
        activity_type=activity_type,
    )


def select_event_candidates(
    events: Iterable[Event],
    start: datetime,
    end: datetime,
    config: RecommendationScoringConfig = DEFAULT_RECOMMENDATION_CONFIG,
) -> CandidateSelection:
    """Evaluate, threshold, diversify lightly, and bound downstream candidates."""
    _validate_selection_config(config)
    evaluations = [evaluate_event(event, start, end, config) for event in events]
    qualified = sorted(
        (
            evaluation
            for evaluation in evaluations
            if evaluation.eligible and evaluation.score >= config.minimum_score
        ),
        key=_evaluation_sort_key,
    )

    selected: list[EventEvaluation] = []
    deferred: list[EventEvaluation] = []
    type_counts: dict[str, int] = {}
    title_counts: dict[str, int] = {}

    for evaluation in qualified:
        activity_type = evaluation.activity_type
        normalized_title = _normalize_text(evaluation.event.title)
        if (
            len(selected) < config.maximum_candidates
            and type_counts.get(activity_type, 0) < config.diversity_soft_cap_per_type
            and title_counts.get(normalized_title, 0) < config.diversity_soft_cap_per_title
        ):
            selected.append(evaluation)
            type_counts[activity_type] = type_counts.get(activity_type, 0) + 1
            title_counts[normalized_title] = title_counts.get(normalized_title, 0) + 1
        else:
            deferred.append(evaluation)

    for evaluation in deferred:
        if len(selected) >= config.maximum_candidates:
            break
        selected.append(evaluation)

    return CandidateSelection(evaluations=evaluations, candidates=selected)


def format_selection_diagnostics(selection: CandidateSelection, top_limit: int = 10) -> str:
    """Render concise local diagnostics without adding them to the digest."""
    lines = [
        f"Raw events after deduplication: {len(selection.evaluations)}",
        f"Eligible: {selection.eligible_count}",
        f"Hard excluded: {selection.excluded_count}",
        f"Candidates selected: {len(selection.candidates)}",
        "",
        "Top deterministic candidates:",
    ]

    if not selection.candidates:
        lines.append("- None")
        return "\n".join(lines)

    for index, evaluation in enumerate(selection.candidates[:top_limit], start=1):
        lines.append(f"{index}. {evaluation.event.title} — score {evaluation.score}")
        lines.append(f"   reasons: {', '.join(evaluation.reasons) or 'no positive signals'}")
    return "\n".join(lines)


def _exclusion_reasons(
    event: Event,
    start: datetime,
    end: datetime,
    config: RecommendationScoringConfig,
) -> list[str]:
    reasons: list[str] = []
    if event.start_time.utcoffset() is None:
        reasons.append("missing timezone-aware start time")
    elif not start <= event.start_time < end:
        reasons.append("outside requested date window")

    if event.end_time is not None:
        if event.end_time.utcoffset() is None:
            reasons.append("missing timezone on end time")
        elif event.end_time <= event.start_time:
            reasons.append("end time is not after start time")

    if not event.city.strip():
        reasons.append("missing usable city or location")

    title_and_categories = _normalize_text(" ".join([event.title, *sorted(event.categories)]))
    all_text = _event_text(event)
    if _contains_any(all_text, config.child_only_terms):
        reasons.append("explicitly child-only event")
    if _contains_any(title_and_categories, config.professional_only_terms):
        reasons.append("explicitly professional or business-only event")
    return reasons


def _event_text(event: Event) -> str:
    return _normalize_text(
        " ".join(
            [
                event.title,
                event.description or "",
                *sorted(event.categories),
            ]
        )
    )


def _strongest_signal_match(
    signal: ScoringSignal,
    *,
    category_texts: tuple[str, ...],
    title_text: str,
    description_text: str,
) -> tuple[str, int] | None:
    if any(_contains_any(category, signal.category_terms) for category in category_texts):
        return "category", signal.category_weight
    if _contains_any(title_text, signal.title_terms):
        return "title", signal.title_weight
    if _contains_any(description_text, signal.description_terms):
        return "description", signal.description_weight
    return None


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    padded_text = f" {text} "
    return any(f" {_normalize_text(term)} " in padded_text for term in terms)


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(part for part in _NON_WORD_PATTERN.split(normalized) if part)


def _evaluation_sort_key(evaluation: EventEvaluation) -> tuple[int, datetime, str, str, str]:
    event = evaluation.event
    return (
        -evaluation.score,
        event.start_time,
        _normalize_text(event.title),
        _normalize_text(event.city),
        event.source_id or "",
    )


def _validate_window(start: datetime, end: datetime) -> None:
    if start.utcoffset() is None or end.utcoffset() is None:
        raise ValueError("Event evaluation requires timezone-aware boundaries.")
    if end <= start:
        raise ValueError("Event evaluation end must be after start.")


def _validate_selection_config(config: RecommendationScoringConfig) -> None:
    if config.maximum_candidates < 1:
        raise ValueError("Maximum candidate count must be positive.")
    if config.diversity_soft_cap_per_type < 1:
        raise ValueError("Diversity soft cap must be positive.")
    if config.diversity_soft_cap_per_title < 1:
        raise ValueError("Per-title diversity soft cap must be positive.")
    if config.description_signal_score_cap < 0:
        raise ValueError("Description signal score cap cannot be negative.")
