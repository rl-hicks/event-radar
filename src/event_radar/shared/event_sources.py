"""Bridge existing event collectors into the neutral regional source contract."""

from __future__ import annotations

import hashlib
from datetime import datetime

from event_radar.collectors.base import EventCollector
from event_radar.models.event import Event
from event_radar.models.regional import (
    ImportantUnknown,
    Location,
    Observation,
    Occurrence,
    Price,
    PriceQuote,
    RegionalOpportunity,
    ResearchScope,
    SourceEvidence,
)
from event_radar.shared.collection import (
    RegionalSourceDescriptor,
    RegionalSourceFailure,
    RegionalSourceResult,
)


class EventCollectorRegionalAdapter:
    def __init__(
        self,
        *,
        descriptor: RegionalSourceDescriptor,
        collector: EventCollector,
        expected_failures: tuple[type[Exception], ...] = (),
    ) -> None:
        if descriptor.opportunity_kinds != ("event",):
            raise ValueError("Event collector adapters must declare only event opportunities.")
        self.descriptor = descriptor
        self._collector = collector
        self._expected_failures = expected_failures

    async def collect(
        self,
        scope: ResearchScope,
        *,
        observed_at: datetime,
    ) -> RegionalSourceResult:
        try:
            events = await self._collector.collect(scope.window.start, scope.window.end)
        except self._expected_failures as exc:
            raise RegionalSourceFailure("unavailable") from exc
        opportunities = tuple(
            event_to_regional_opportunity(
                event,
                source_id=self.descriptor.source_id,
                scope=scope,
                observed_at=observed_at,
            )
            for event in events
        )
        return RegionalSourceResult(opportunities=opportunities)


def event_to_regional_opportunity(
    event: Event,
    *,
    source_id: str,
    scope: ResearchScope,
    observed_at: datetime,
) -> RegionalOpportunity:
    if event.alternate_sources:
        raise ValueError(
            "Source adapters require source-native events before cross-source deduplication."
        )
    record = event.source_id or str(event.source_url)
    evidence_id = _stable_id("evidence", source_id, record, event.start_time.isoformat())
    occurrence_id = _stable_id("occurrence", source_id, record, event.start_time.isoformat())
    opportunity_id = _stable_id("event", source_id, record, event.start_time.isoformat())

    claims: list[str] = ["existence", "location", "time"]
    if event.description or event.categories:
        claims.append("description")
    price = _price(event, evidence_id)
    if price.state != "unknown":
        claims.append("price")

    evidence = SourceEvidence(
        evidence_id=evidence_id,
        source_id=source_id,
        url=event.source_url,
        source_record_id=event.source_id,
        observed_at=observed_at,
        published_at=None,
        claims=tuple(claims),
        summary=event.description or f"Public event listing for {event.title}.",
        confidence="high",
        occurrence_start=event.start_time,
        occurrence_end=event.end_time,
    )
    location = Location(
        country_code="US",
        subdivision_code=event.state,
        county=scope.region.county,
        city=event.city,
        venue=event.venue,
        evidence_ids=(evidence_id,),
    )
    unknowns = [
        ImportantUnknown(
            kind="availability",
            detail="Current ticket or attendance availability is unverified.",
        ),
        ImportantUnknown(
            kind="semantic_analysis",
            detail="Shared semantic analysis has not run yet.",
        ),
    ]
    if price.state == "unknown":
        unknowns.append(
            ImportantUnknown(
                kind="price",
                detail="Source did not establish a usable price.",
            )
        )

    categories = (
        Observation[tuple[str, ...]](
            state="known",
            value=tuple(sorted(event.categories)),
            evidence_ids=(evidence_id,),
        )
        if event.categories
        else Observation[tuple[str, ...]](
            state="unknown",
            value=None,
            evidence_ids=(),
        )
    )
    return RegionalOpportunity(
        opportunity_id=opportunity_id,
        kind="event",
        title=event.title,
        location=location,
        evidence=(evidence,),
        semantics=None,
        categories=categories,
        occurrences=(
            Occurrence(
                occurrence_id=occurrence_id,
                start=event.start_time,
                end=event.end_time,
                location=location,
                evidence_ids=(evidence_id,),
                price=price,
                available=Observation[bool](
                    state="unknown",
                    value=None,
                    evidence_ids=(),
                ),
            ),
        ),
        route=None,
        access_open=Observation[bool](
            state="unknown",
            value=None,
            evidence_ids=(),
        ),
        unknowns=tuple(unknowns),
    )


def _price(event: Event, evidence_id: str) -> Price:
    if event.price_conflict:
        return Price(state="unknown", quotes=())
    numeric = event.price_min is not None or event.price_max is not None
    if numeric and event.price_currency is None:
        return Price(state="unknown", quotes=())
    if not numeric and event.price_details is None:
        return Price(state="unknown", quotes=())
    return Price(
        state="known",
        quotes=(
            PriceQuote(
                minimum=event.price_min,
                maximum=event.price_max,
                currency=event.price_currency,
                details=event.price_details,
                evidence_ids=(evidence_id,),
            ),
        ),
    )


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:20]
    return f"{prefix}-{digest}"
