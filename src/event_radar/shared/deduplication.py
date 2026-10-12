"""Conservative cross-source deduplication for neutral regional opportunities."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC

from pydantic import StrictBool

from event_radar.models.regional import (
    FactualExclusion,
    ImportantUnknown,
    Location,
    Observation,
    Occurrence,
    Price,
    PriceQuote,
    RegionalOpportunity,
)

_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class RegionalDeduplicationResult:
    opportunities: tuple[RegionalOpportunity, ...]
    exclusions: tuple[FactualExclusion, ...]
    duplicates_removed: int


def deduplicate_regional_opportunities(
    opportunities: tuple[RegionalOpportunity, ...],
    *,
    preferred_opportunity_ids: frozenset[str] | None = None,
) -> RegionalDeduplicationResult:
    retained: list[RegionalOpportunity] = []
    exclusions: list[FactualExclusion] = []
    removed = 0

    for candidate in sorted(opportunities, key=_sort_key):
        duplicate_index = next(
            (
                index
                for index, existing in enumerate(retained)
                if _same_event_occurrence(existing, candidate)
            ),
            None,
        )
        if duplicate_index is None:
            retained.append(candidate)
            continue

        existing = retained[duplicate_index]
        merged, dropped = _merge_pair(
            existing,
            candidate,
            preferred_opportunity_ids=preferred_opportunity_ids,
        )
        retained[duplicate_index] = merged
        removed += 1
        for evidence in dropped.evidence:
            exclusions.append(
                FactualExclusion(
                    source_id=evidence.source_id,
                    source_record_id=evidence.source_record_id or evidence.evidence_id,
                    reason="duplicate_occurrence",
                    duplicate_of=merged.occurrences[0].occurrence_id,
                )
            )

    return RegionalDeduplicationResult(tuple(retained), tuple(exclusions), removed)


def _same_event_occurrence(first: RegionalOpportunity, second: RegionalOpportunity) -> bool:
    if first.kind != "event" or second.kind != "event":
        return False
    if len(first.occurrences) != 1 or len(second.occurrences) != 1:
        return False
    a, b = first.occurrences[0], second.occurrences[0]
    if _normalize(first.title) != _normalize(second.title):
        return False
    if a.start.astimezone(UTC) != b.start.astimezone(UTC):
        return False
    if _normalize(a.location.city or "") != _normalize(b.location.city or ""):
        return False
    if a.location.venue and b.location.venue:
        if _normalize(a.location.venue) != _normalize(b.location.venue):
            return False
    if a.end is not None and b.end is not None:
        if a.end.astimezone(UTC) != b.end.astimezone(UTC):
            return False
    return True


def _merge_pair(
    first: RegionalOpportunity,
    second: RegionalOpportunity,
    *,
    preferred_opportunity_ids: frozenset[str] | None,
) -> tuple[RegionalOpportunity, RegionalOpportunity]:
    preferred = preferred_opportunity_ids or frozenset()
    if first.opportunity_id in preferred and second.opportunity_id not in preferred:
        primary = first
    elif second.opportunity_id in preferred and first.opportunity_id not in preferred:
        primary = second
    else:
        primary = sorted((first, second), key=_preference_key)[0]
    dropped = second if primary is first else first
    a = primary.occurrences[0]
    b = dropped.occurrences[0]
    evidence = tuple(
        sorted((*primary.evidence, *dropped.evidence), key=lambda item: item.evidence_id)
    )
    location = _merge_location(primary.location, dropped.location)
    occurrence_location = _merge_location(a.location, b.location)
    unknowns = _merge_unknowns(primary.unknowns, dropped.unknowns)

    occurrence = Occurrence(
        occurrence_id=primary.occurrences[0].occurrence_id,
        start=a.start,
        end=a.end if a.end is not None else b.end,
        location=occurrence_location,
        evidence_ids=tuple(sorted(set((*a.evidence_ids, *b.evidence_ids)))),
        price=_merge_price(a.price, b.price),
        available=_merge_bool_observation(a.available, b.available),
    )
    categories = _merge_categories(primary.categories, dropped.categories)
    access = _merge_bool_observation(primary.access_open, dropped.access_open)
    if (
        primary.access_open.state == "known"
        and dropped.access_open.state == "known"
        and primary.access_open.value != dropped.access_open.value
    ):
        unknowns = _append_unknown(
            unknowns,
            ImportantUnknown(
                kind="access",
                detail="Sources conflict on current access status.",
            ),
        )
    if (
        a.available.state == "known"
        and b.available.state == "known"
        and a.available.value != b.available.value
    ):
        unknowns = _append_unknown(
            unknowns,
            ImportantUnknown(
                kind="availability",
                detail="Sources conflict on current availability.",
            ),
        )

    return (
        RegionalOpportunity(
            opportunity_id=primary.opportunity_id,
            kind="event",
            title=primary.title,
            location=location,
            evidence=evidence,
            semantics=primary.semantics if primary.semantics == dropped.semantics else None,
            categories=categories,
            occurrences=(occurrence,),
            route=None,
            access_open=access,
            unknowns=unknowns,
        ),
        dropped,
    )


def _merge_price(first: Price, second: Price) -> Price:
    quotes = [*first.quotes, *second.quotes]
    if not quotes:
        return Price(state="unknown", quotes=())
    groups: dict[tuple[object, ...], list[PriceQuote]] = {}
    for quote in quotes:
        key = (quote.minimum, quote.maximum, quote.currency, quote.details)
        groups.setdefault(key, []).append(quote)
    reconciled: list[PriceQuote] = []
    for values in groups.values():
        quote = values[0]
        reconciled.append(
            PriceQuote(
                minimum=quote.minimum,
                maximum=quote.maximum,
                currency=quote.currency,
                details=quote.details,
                evidence_ids=tuple(sorted({eid for item in values for eid in item.evidence_ids})),
            )
        )
    return Price(
        state="known" if len(reconciled) == 1 else "conflicting",
        quotes=tuple(reconciled),
    )


def _merge_categories(
    first: Observation[tuple[str, ...]],
    second: Observation[tuple[str, ...]],
) -> Observation[tuple[str, ...]]:
    known = [item for item in (first, second) if item.state == "known"]
    if not known:
        return Observation[tuple[str, ...]](
            state="unknown",
            value=None,
            evidence_ids=(),
        )
    return Observation[tuple[str, ...]](
        state="known",
        value=tuple(sorted({value for item in known for value in (item.value or ())})),
        evidence_ids=tuple(sorted({eid for item in known for eid in item.evidence_ids})),
    )


def _merge_bool_observation(
    first: Observation[StrictBool],
    second: Observation[StrictBool],
) -> Observation[StrictBool]:
    known = [item for item in (first, second) if item.state == "known"]
    if not known:
        return Observation[StrictBool](state="unknown", value=None, evidence_ids=())
    values = {item.value for item in known}
    if len(values) != 1:
        return Observation[StrictBool](state="unknown", value=None, evidence_ids=())
    return Observation[StrictBool](
        state="known",
        value=known[0].value,
        evidence_ids=tuple(sorted({eid for item in known for eid in item.evidence_ids})),
    )


def _merge_location(first: Location, second: Location) -> Location:
    preferred = first if _location_score(first) >= _location_score(second) else second
    return Location(
        country_code=preferred.country_code,
        subdivision_code=preferred.subdivision_code,
        county=preferred.county,
        city=preferred.city,
        venue=preferred.venue,
        evidence_ids=tuple(sorted(set((*first.evidence_ids, *second.evidence_ids)))),
    )


def _location_score(value: Location) -> tuple[int, str, str]:
    return (
        int(value.city is not None) + int(value.venue is not None),
        value.city or "",
        value.venue or "",
    )


def _merge_unknowns(
    first: tuple[ImportantUnknown, ...],
    second: tuple[ImportantUnknown, ...],
) -> tuple[ImportantUnknown, ...]:
    unique = {(item.kind, item.detail): item for item in (*first, *second)}
    return tuple(unique[key] for key in sorted(unique))


def _append_unknown(
    values: tuple[ImportantUnknown, ...],
    item: ImportantUnknown,
) -> tuple[ImportantUnknown, ...]:
    return _merge_unknowns(values, (item,))


def _preference_key(value: RegionalOpportunity) -> tuple[int, str]:
    occurrence = value.occurrences[0]
    completeness = sum(
        item is not None
        for item in (
            value.location.venue,
            occurrence.end,
            occurrence.price.quotes[0] if occurrence.price.quotes else None,
            value.categories.value,
        )
    )
    return (-completeness, value.opportunity_id)


def _sort_key(value: RegionalOpportunity) -> tuple[object, ...]:
    if value.kind == "event" and value.occurrences:
        return (0, value.occurrences[0].start.astimezone(UTC), value.opportunity_id)
    return (1, value.opportunity_id)


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(part for part in _NON_WORD.split(normalized) if part)
