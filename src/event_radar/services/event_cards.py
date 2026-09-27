import hashlib
import re
import unicodedata
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from pydantic import HttpUrl

from event_radar.curation_config import DEFAULT_CURATION_CONFIG, CurationConfig
from event_radar.models.direction import Direction
from event_radar.models.event import Event
from event_radar.models.event_analysis import (
    EventDisposition,
    EventOccurrenceFact,
    EventOrigin,
    EventSourceFact,
    ScrapedEventAnalysis,
    ScrapedEventAnalysisRequest,
    ScrapedEventJudgment,
    SemanticConfidence,
    WeekendEventCard,
)
from event_radar.models.user_context import UserContext, structured_runtime_context
from event_radar.models.web_discovery import (
    DiscoveredEvent,
    ExistingEventIdentity,
    WebDiscoveryRequest,
)
from event_radar.services.recommendation_context import event_candidate_id

_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)


class EventAnalysisReferenceError(ValueError):
    """Raised when semantic analysis does not correspond to supplied event facts."""


def build_scraped_analysis_request(
    *,
    generated_at: datetime,
    weekend_start: datetime,
    weekend_end: datetime,
    user_context: UserContext,
    personal_experience_context: str,
    permanent_directions: list[Direction],
    temporary_directions: list[Direction],
    events: list[Event],
    config: CurationConfig = DEFAULT_CURATION_CONFIG,
) -> ScrapedEventAnalysisRequest:
    return ScrapedEventAnalysisRequest(
        generated_at=generated_at,
        weekend_start=weekend_start,
        weekend_end=weekend_end,
        user_context=structured_runtime_context(user_context),
        personal_experience_context=personal_experience_context,
        permanent_directions=[direction.text for direction in permanent_directions],
        temporary_directions=[direction.text for direction in temporary_directions],
        events=[event_occurrence_fact(event, config=config) for event in events],
    )


def event_occurrence_fact(
    event: Event,
    *,
    config: CurationConfig = DEFAULT_CURATION_CONFIG,
) -> EventOccurrenceFact:
    return EventOccurrenceFact(
        event_id=event_candidate_id(event),
        title=event.title,
        start_time=event.start_time,
        end_time=event.end_time,
        venue=event.venue,
        city=event.city,
        state=event.state,
        categories=sorted(event.categories),
        description=_bounded(event.description, config.event_description_max_characters),
        price_min=event.price_min,
        price_max=event.price_max,
        price_currency=event.price_currency,
        price_details=event.price_details,
        price_conflict=event.price_conflict,
        sources=[
            EventSourceFact(
                source_name=event.source_name,
                source_id=event.source_id,
                source_url=event.source_url,
            ),
            *[
                EventSourceFact(
                    source_name=source.source_name,
                    source_id=source.source_id,
                    source_url=source.source_url,
                )
                for source in event.alternate_sources
            ],
        ],
    )


def validate_scraped_analysis(
    request: ScrapedEventAnalysisRequest,
    analysis: ScrapedEventAnalysis,
) -> None:
    expected = {event.event_id for event in request.events}
    analyzed = [judgment.event_id for judgment in analysis.events]
    if len(analyzed) != len(set(analyzed)):
        raise EventAnalysisReferenceError("Scraped analysis repeated an event ID.")
    if set(analyzed) != expected:
        raise EventAnalysisReferenceError(
            "Scraped analysis must reference every supplied event exactly once."
        )

    grouped: set[str] = set()
    group_ids = {group.group_id for group in analysis.experience_groups}
    if len(group_ids) != len(analysis.experience_groups):
        raise EventAnalysisReferenceError("Experience group IDs must be unique.")
    for group in analysis.experience_groups:
        members = set(group.occurrence_ids)
        if not members <= expected:
            raise EventAnalysisReferenceError("Experience group referenced an unknown event ID.")
        if len(members) != len(group.occurrence_ids):
            raise EventAnalysisReferenceError("Experience group repeated an occurrence ID.")
        if grouped & members:
            raise EventAnalysisReferenceError("An occurrence appeared in multiple groups.")
        grouped.update(members)

    membership = {
        occurrence_id: group.group_id
        for group in analysis.experience_groups
        for occurrence_id in group.occurrence_ids
    }
    for judgment in analysis.events:
        if judgment.experience_group_id is None:
            if judgment.event_id in membership:
                raise EventAnalysisReferenceError("Grouped occurrence omitted its group ID.")
        elif (
            judgment.experience_group_id not in group_ids
            or membership.get(judgment.event_id) != judgment.experience_group_id
        ):
            raise EventAnalysisReferenceError("Judgment used an invalid experience group ID.")


def build_scraped_event_cards(
    request: ScrapedEventAnalysisRequest,
    analysis: ScrapedEventAnalysis | None,
) -> list[WeekendEventCard]:
    facts = {event.event_id: event for event in request.events}
    if analysis is None:
        return [_factual_fallback_card(event) for event in request.events]

    validate_scraped_analysis(request, analysis)
    judgments = {judgment.event_id: judgment for judgment in analysis.events}
    grouped_ids: set[str] = set()
    cards: list[WeekendEventCard] = []

    for group in analysis.experience_groups:
        group_judgments = [judgments[event_id] for event_id in group.occurrence_ids]
        if not any(
            judgment.disposition in {EventDisposition.RETAIN, EventDisposition.BORDERLINE}
            for judgment in group_judgments
        ):
            grouped_ids.update(group.occurrence_ids)
            continue
        occurrences = sorted(
            (facts[event_id] for event_id in group.occurrence_ids),
            key=lambda occurrence: occurrence.start_time,
        )
        lead = min(group_judgments, key=_judgment_priority)
        cards.append(
            _card_from_judgment(
                candidate_id=_group_candidate_id(group.occurrence_ids),
                title=occurrences[0].title,
                occurrences=occurrences,
                judgment=lead,
                group_judgments=group_judgments,
            )
        )
        grouped_ids.update(group.occurrence_ids)

    for judgment in analysis.events:
        if judgment.event_id in grouped_ids or judgment.disposition is EventDisposition.REJECT:
            continue
        fact = facts[judgment.event_id]
        cards.append(
            _card_from_judgment(
                candidate_id=fact.event_id,
                title=fact.title,
                occurrences=[fact],
                judgment=judgment,
                group_judgments=[judgment],
            )
        )
    return sorted(cards, key=lambda card: (card.occurrences[0].start_time, card.title.casefold()))


def build_web_discovery_request(
    request: ScrapedEventAnalysisRequest,
    *,
    personal_experience_context: str,
) -> WebDiscoveryRequest:
    return WebDiscoveryRequest(
        generated_at=request.generated_at,
        weekend_start=request.weekend_start,
        weekend_end=request.weekend_end,
        user_context=request.user_context,
        personal_experience_context=personal_experience_context,
        permanent_directions=request.permanent_directions,
        temporary_directions=request.temporary_directions,
        existing_events=[
            ExistingEventIdentity(
                title=event.title,
                start_time=event.start_time,
                city=event.city,
                venue=event.venue,
                source_urls=[source.source_url for source in event.sources],
            )
            for event in request.events
        ],
    )


def remove_exact_web_duplicates(
    discoveries: list[DiscoveredEvent],
    scraped_events: list[EventOccurrenceFact],
    *,
    timezone: str,
) -> tuple[list[DiscoveredEvent], int]:
    zone = ZoneInfo(timezone)
    existing = {
        _identity(event.title, event.start_time, event.city, event.venue, zone)
        for event in scraped_events
    }
    retained: list[DiscoveredEvent] = []
    seen = set(existing)
    duplicates = 0
    for discovery in discoveries:
        identity = _identity(
            discovery.title,
            discovery.start_time,
            discovery.city,
            discovery.venue,
            zone,
        )
        if identity in seen:
            duplicates += 1
            continue
        seen.add(identity)
        retained.append(discovery)
    return retained, duplicates


def build_web_event_cards(discoveries: list[DiscoveredEvent]) -> list[WeekendEventCard]:
    cards: list[WeekendEventCard] = []
    for discovery in discoveries:
        occurrence = EventOccurrenceFact(
            event_id=discovery.discovery_id,
            title=discovery.title,
            start_time=discovery.start_time,
            end_time=discovery.end_time,
            venue=discovery.venue,
            city=discovery.city,
            state=discovery.state,
            categories=[],
            description=discovery.description_evidence,
            price_min=_decimal_price(discovery.price_min),
            price_max=_decimal_price(discovery.price_max),
            price_currency=discovery.price_currency,
            price_details=discovery.price_details,
            sources=[
                EventSourceFact(
                    source_name=source.source_name,
                    source_id=None,
                    source_url=HttpUrl(source.source_url),
                    supported_claims=source.supported_claims,
                    source_confidence=source.source_confidence,
                )
                for source in discovery.evidence_sources
            ],
        )
        cards.append(
            WeekendEventCard(
                candidate_id=discovery.discovery_id,
                origin=EventOrigin.WEB_DISCOVERED,
                title=discovery.title,
                occurrences=[occurrence],
                experience_summary=discovery.experience_summary,
                experience_modes=discovery.experience_modes,
                interaction_architecture=discovery.interaction_architecture,
                solo_viability=discovery.solo_viability,
                active_value=discovery.active_value,
                distinctiveness=discovery.distinctiveness,
                social_opportunity=discovery.social_opportunity,
                friction_summary=discovery.friction_summary,
                schedule_observation=discovery.schedule_observation,
                uncertainties=discovery.uncertainties,
                source_confidence=_lowest_source_confidence(discovery),
                verification_confidence=discovery.verification_confidence,
                semantic_analysis_available=True,
            )
        )
    return cards


def _card_from_judgment(
    *,
    candidate_id: str,
    title: str,
    occurrences: list[EventOccurrenceFact],
    judgment: ScrapedEventJudgment,
    group_judgments: list[ScrapedEventJudgment],
) -> WeekendEventCard:
    return WeekendEventCard(
        candidate_id=candidate_id,
        origin=EventOrigin.SCRAPED,
        title=title,
        occurrences=occurrences,
        experience_summary=judgment.experience_summary,
        experience_modes=sorted(
            {mode for value in group_judgments for mode in value.experience_modes}
        ),
        interaction_architecture=judgment.interaction_architecture,
        solo_viability=judgment.solo_viability,
        active_value=judgment.active_value,
        distinctiveness=judgment.distinctiveness,
        social_opportunity=judgment.social_opportunity,
        friction_summary=judgment.friction_summary,
        schedule_observation=judgment.schedule_observation,
        uncertainties=list(
            dict.fromkeys(item for value in group_judgments for item in value.uncertainties)
        ),
        source_confidence=judgment.confidence,
        verification_confidence=None,
        semantic_analysis_available=True,
    )


def _factual_fallback_card(event: EventOccurrenceFact) -> WeekendEventCard:
    unavailable = "Semantic event analysis unavailable; preserve for downstream factual review."
    return WeekendEventCard(
        candidate_id=event.event_id,
        origin=EventOrigin.SCRAPED,
        title=event.title,
        occurrences=[event],
        experience_summary=event.description or "Source supplied no event description.",
        experience_modes=[],
        interaction_architecture="Unknown without semantic analysis.",
        solo_viability="Unknown without semantic analysis.",
        active_value="Unknown without semantic analysis.",
        distinctiveness="Unknown without semantic analysis.",
        social_opportunity="Unknown without semantic analysis.",
        friction_summary="Travel friction is not calculated.",
        schedule_observation="Use authoritative occurrence time and recurring availability.",
        uncertainties=[unavailable],
        source_confidence=SemanticConfidence.UNKNOWN,
        verification_confidence=None,
        semantic_analysis_available=False,
    )


def _decimal_price(value: float | None) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _lowest_source_confidence(discovery: DiscoveredEvent) -> SemanticConfidence:
    order = {
        SemanticConfidence.UNKNOWN: 0,
        SemanticConfidence.LOW: 1,
        SemanticConfidence.MODERATE: 2,
        SemanticConfidence.HIGH: 3,
    }
    return min(
        (source.source_confidence for source in discovery.evidence_sources),
        key=order.__getitem__,
    )


def _judgment_priority(judgment: ScrapedEventJudgment) -> tuple[int, str]:
    order = {
        EventDisposition.RETAIN: 0,
        EventDisposition.BORDERLINE: 1,
        EventDisposition.REJECT: 2,
    }
    return order[judgment.disposition], judgment.event_id


def _group_candidate_id(occurrence_ids: list[str]) -> str:
    digest = hashlib.sha256("|".join(sorted(occurrence_ids)).encode()).hexdigest()[:20]
    return f"event_group_{digest}"


def _identity(
    title: str,
    start_time: datetime,
    city: str,
    venue: str | None,
    timezone: ZoneInfo,
) -> tuple[str, str, str, str]:
    local = start_time.astimezone(timezone)
    return (
        _normalize(title),
        local.isoformat(),
        _normalize(city),
        _normalize(venue or ""),
    )


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(part for part in _NON_WORD.split(normalized) if part)


def _bounded(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."
