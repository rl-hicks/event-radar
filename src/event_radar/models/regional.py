"""Neutral regional wire contracts. No legacy models, settings, services or I/O.

Validate external data with model_validate_json; model_construct/model_copy(update=...)
are Pydantic's trusted bypasses and must not be used at ingestion boundaries.
"""

import re
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from ipaddress import ip_address
from typing import Annotated, Literal
from urllib.parse import parse_qsl
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StrictBool,
    field_validator,
    model_validator,
)

Text = Annotated[
    str,
    Field(min_length=1),
    AfterValidator(lambda value: value if value.strip() else _invalid_text()),
]
Identifier = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=120)]
Count = Annotated[int, Field(ge=0, strict=True)]
Amount = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
Confidence = Literal["high", "moderate", "low", "unknown"]
Claim = Literal["existence", "location", "time", "price", "description", "access", "availability", "route"]


def _invalid_text() -> str:
    raise ValueError("Text must not be blank.")


def _instant(value: datetime) -> datetime:
    """Compare real instants, including the repeated local hour at DST fall-back."""
    return value.astimezone(UTC)


# Bounded, canonical citation policy. These are event selectors, not an invitation
# to accept arbitrary provider queries or to silently strip an identifying query.
_PUBLIC_SELECTORS = frozenset({
    "event", "event_id", "eventid", "eid", "id", "listing_id", "occurrence_id",
    "post_id", "p", "slug",
})
_PUBLIC_SELECTOR_VALUE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._~-]{0,127}\Z", re.ASCII)
_BLOCKED_HOST_SUFFIXES = (
    ".localhost", ".local", ".internal", ".lan", ".home", ".onion",
    ".test", ".invalid", ".example", ".arpa", ".corp", ".intranet",
)


def _validate_public_evidence_url(url: HttpUrl) -> None:
    """Syntactic guard only; callers must not fetch/resolve untrusted URLs directly."""
    host = (url.host or "").lower()
    if url.scheme != "https" or url.port not in (None, 443) or url.username or url.password or url.fragment:
        raise ValueError("Evidence requires a canonical HTTPS URL without credentials/fragment.")
    if (
        not host or host.endswith(".") or "." not in host
        or host in {"localhost", "metadata.google.internal"}
        or host.endswith(_BLOCKED_HOST_SUFFIXES)
        or not re.fullmatch(r"[a-z0-9.-]+", host, re.ASCII)
        or all(part.isdigit() for part in host.split("."))
    ):
        raise ValueError("Evidence URL requires a public DNS hostname.")
    try:
        ip_address(host.strip("[]"))
    except ValueError:
        pass
    else:
        raise ValueError("IP-literal evidence URLs are not permitted.")
    if url.query:
        try:
            pairs = parse_qsl(url.query, keep_blank_values=True, strict_parsing=True, max_num_fields=4)
        except ValueError as exc:
            raise ValueError("Evidence URL query is not a bounded event selector.") from exc
        keys = [key.lower() for key, _ in pairs]
        if len(keys) != len(set(keys)) or any(
            key not in _PUBLIC_SELECTORS or _PUBLIC_SELECTOR_VALUE.fullmatch(value) is None
            for (key, value) in pairs
        ):
            raise ValueError("Evidence URL query must contain only canonical event selectors.")


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class Region(Contract):
    region_id: Literal["sonoma-county-ca"]
    country_code: Literal["US"]
    subdivision_code: Literal["CA"]
    county: Literal["Sonoma County"]
    timezone: Literal["America/Los_Angeles"]

    @model_validator(mode="after")
    def valid_timezone(self) -> "Region":
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Region timezone must be an IANA timezone.") from exc
        return self


SONOMA_COUNTY = Region(
    region_id="sonoma-county-ca",
    country_code="US",
    subdivision_code="CA",
    county="Sonoma County",
    timezone="America/Los_Angeles",
)


class WeekendWindow(Contract):
    """A calendar interval, never truncated to the current time."""

    friday: date
    timezone: Text

    @model_validator(mode="after")
    def valid_weekend(self) -> "WeekendWindow":
        if self.friday.weekday() != 4:
            raise ValueError("Weekend must be anchored on Friday.")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Weekend timezone must be an IANA timezone.") from exc
        return self

    @property
    def start(self) -> datetime:
        return datetime.combine(self.friday, time.min, ZoneInfo(self.timezone))

    @property
    def end(self) -> datetime:
        return datetime.combine(self.friday + timedelta(days=3), time.min, ZoneInfo(self.timezone))

    def overlaps(self, start: datetime, end: datetime | None) -> bool:
        if start.utcoffset() is None or (end is not None and end.utcoffset() is None):
            raise ValueError("Occurrence times must be aware.")
        start = start.astimezone(UTC)
        end = end.astimezone(UTC) if end is not None else None
        lower, upper = self.start.astimezone(UTC), self.end.astimezone(UTC)
        return lower <= start < upper if end is None else start < upper and end > lower


class ResearchIdentity(Contract):
    region_id: Identifier
    friday: date
    research_policy_version: Identifier

    @field_validator("friday")
    @classmethod
    def friday_anchor(cls, value: date) -> date:
        if value.weekday() != 4:
            raise ValueError("Research identity must be anchored on Friday.")
        return value

    @property
    def key(self) -> str:
        return f"{self.region_id}/{self.friday.isoformat()}/{self.research_policy_version}"


class ResearchScope(Contract):
    region: Region
    window: WeekendWindow
    research_policy_version: Identifier
    as_of: AwareDatetime

    @model_validator(mode="after")
    def matching_timezone(self) -> "ResearchScope":
        if self.region.timezone != self.window.timezone:
            raise ValueError("Region and weekend timezones must match.")
        return self

    @property
    def identity(self) -> ResearchIdentity:
        return ResearchIdentity(
            region_id=self.region.region_id,
            friday=self.window.friday,
            research_policy_version=self.research_policy_version,
        )


class Observation[T](Contract):
    """Known false/zero/empty values are not unknown. No implicit default."""

    state: Literal["unknown", "known"]
    value: T | None
    evidence_ids: tuple[Identifier, ...]

    @model_validator(mode="after")
    def valid_state(self) -> "Observation[T]":
        if self.state == "unknown":
            if self.value is not None or self.evidence_ids:
                raise ValueError("Unknown observations have null value and no evidence.")
        elif self.value is None or not self.evidence_ids:
            raise ValueError("Known observations require a value and evidence.")
        _unique(self.evidence_ids)
        return self


class SourceEvidence(Contract):
    evidence_id: Identifier
    source_id: Identifier
    url: HttpUrl
    source_record_id: Text | None
    observed_at: AwareDatetime
    published_at: AwareDatetime | None
    claims: tuple[Claim, ...] = Field(min_length=1)
    summary: Text
    confidence: Confidence
    occurrence_start: AwareDatetime | None
    occurrence_end: AwareDatetime | None

    @model_validator(mode="after")
    def valid_evidence(self) -> "SourceEvidence":
        _unique(self.claims)
        _validate_public_evidence_url(self.url)
        if ("time" in self.claims) != (self.occurrence_start is not None):
            raise ValueError("Time evidence requires an extracted occurrence start.")
        if self.occurrence_end is not None and (
            self.occurrence_start is None or _instant(self.occurrence_end) <= _instant(self.occurrence_start)
        ):
            raise ValueError("Evidence end must follow start.")
        if self.published_at is not None and _instant(self.published_at) > _instant(self.observed_at):
            raise ValueError("Publication cannot follow observation.")
        return self


class Location(Contract):
    country_code: Literal["US"]
    subdivision_code: Text
    county: Text
    city: Text | None
    venue: Text | None
    evidence_ids: tuple[Identifier, ...] = Field(min_length=1)


class PriceQuote(Contract):
    minimum: Amount | None
    maximum: Amount | None
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")] | None
    details: Text | None
    evidence_ids: tuple[Identifier, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_quote(self) -> "PriceQuote":
        if self.minimum is None and self.maximum is None and self.details is None:
            raise ValueError("A quote needs an amount or source-described terms.")
        if (self.minimum is not None or self.maximum is not None) and self.currency is None:
            raise ValueError("Numeric prices require a currency.")
        if self.minimum is not None and self.maximum is not None and self.maximum < self.minimum:
            raise ValueError("Price maximum must not be below minimum.")
        return self


class Price(Contract):
    state: Literal["unknown", "known", "conflicting"]
    quotes: tuple[PriceQuote, ...]

    @model_validator(mode="after")
    def valid_price(self) -> "Price":
        if self.state == "unknown" and self.quotes:
            raise ValueError("Unknown price has no quotes.")
        if self.state == "known" and len(self.quotes) != 1:
            raise ValueError("Known price has one reconciled quote with all supporting sources.")
        if self.state == "conflicting":
            values = {(q.minimum, q.maximum, q.currency, q.details) for q in self.quotes}
            if len(values) < 2:
                raise ValueError("Conflicting price preserves at least two different claims.")
        return self


class SemanticDescriptor(Contract):
    kind: Literal["experience", "participation", "interaction", "setting", "logistics"]
    description: Text
    evidence_ids: tuple[Identifier, ...] = Field(min_length=1)
    confidence: Confidence


class ImportantUnknown(Contract):
    kind: Literal[
        "price",
        "access",
        "availability",
        "weather",
        "route",
        "location",
        "time",
        "description",
        "source_coverage",
        "semantic_analysis",
    ]
    detail: Text


class Occurrence(Contract):
    occurrence_id: Identifier
    start: AwareDatetime
    end: AwareDatetime | None
    location: Location
    evidence_ids: tuple[Identifier, ...] = Field(min_length=1)
    price: Price
    available: Observation[StrictBool]

    @model_validator(mode="after")
    def valid_interval(self) -> "Occurrence":
        if self.end is not None and _instant(self.end) <= _instant(self.start):
            raise ValueError("Occurrence end must follow start.")
        return self


class RouteFacts(Contract):
    distance_miles: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)] | None
    elevation_gain_ft: Count | None
    route_description: Text | None
    evidence_ids: tuple[Identifier, ...] = Field(min_length=1)


class RegionalOpportunity(Contract):
    opportunity_id: Identifier
    kind: Literal["event", "hike"]
    title: Text
    location: Location
    evidence: tuple[SourceEvidence, ...] = Field(min_length=1)
    # null = not established; [] = assessed with no supported descriptors.
    semantics: tuple[SemanticDescriptor, ...] | None
    categories: Observation[tuple[Text, ...]]
    occurrences: tuple[Occurrence, ...]
    route: RouteFacts | None
    access_open: Observation[StrictBool]
    unknowns: tuple[ImportantUnknown, ...]

    @model_validator(mode="after")
    def validate_evidence_and_identity(self) -> "RegionalOpportunity":
        _unique(tuple(e.evidence_id for e in self.evidence))
        _unique(tuple(o.occurrence_id for o in self.occurrences))
        registry = {e.evidence_id: e for e in self.evidence}

        def require(ids: tuple[str, ...], claim: Claim) -> None:
            _unique(ids)
            if not ids or any(i not in registry or claim not in registry[i].claims for i in ids):
                raise ValueError("Missing or incompatible claim evidence.")

        if not any("existence" in e.claims for e in self.evidence):
            raise ValueError("An opportunity needs existence evidence.")
        require(self.location.evidence_ids, "location")
        for descriptor in self.semantics or ():
            require(descriptor.evidence_ids, "description")
        if self.categories.state == "known":
            require(self.categories.evidence_ids, "description")
        if self.access_open.state == "known":
            require(self.access_open.evidence_ids, "access")
        if self.kind == "event" and (not self.occurrences or self.route is not None):
            raise ValueError("Events require occurrences and do not carry independent hike routes.")
        if self.kind == "hike" and (self.occurrences or self.route is None):
            raise ValueError("Independent hikes require route facts, not invented scheduled times.")
        if self.route is not None:
            require(self.route.evidence_ids, "route")
        signatures = []
        for occurrence in self.occurrences:
            require(occurrence.location.evidence_ids, "location")
            require(occurrence.evidence_ids, "time")
            if any(
                _instant(registry[i].occurrence_start) != _instant(occurrence.start)
                or (
                    registry[i].occurrence_end is not None
                    and (occurrence.end is None or _instant(registry[i].occurrence_end) != _instant(occurrence.end))
                )
                for i in occurrence.evidence_ids
            ):
                raise ValueError("Occurrence times must match source-extracted evidence.")
            if occurrence.end is not None and not any(
                registry[i].occurrence_end is not None
                and _instant(registry[i].occurrence_end) == _instant(occurrence.end)
                for i in occurrence.evidence_ids
            ):
                raise ValueError("Known occurrence end requires matching end-time evidence.")
            for quote in occurrence.price.quotes:
                require(quote.evidence_ids, "price")
            if occurrence.available.state == "known":
                require(occurrence.available.evidence_ids, "availability")
            # Only exact, fully located duplicates; unknown venue is not an identity.
            if occurrence.location.venue is not None and occurrence.location.city is not None:
                signatures.append(
                    (
                        occurrence.start.astimezone(UTC),
                        _instant(occurrence.end) if occurrence.end is not None else None,
                        occurrence.location.country_code,
                        occurrence.location.subdivision_code,
                        occurrence.location.county,
                        occurrence.location.city,
                        occurrence.location.venue,
                    )
                )
        if len(signatures) != len(set(signatures)):
            raise ValueError("Exact duplicate occurrences must combine provenance.")
        return self


FailureCode = Literal[
    "timeout", "unavailable", "invalid_response", "rate_limited", "not_configured"
]
SourceState = Literal["success", "partial", "failed", "not_attempted"]


class SourceCoverage(Contract):
    source_id: Identifier
    channel: Literal["fixed_feed", "complementary_discovery", "hike_catalog", "weather"]+    scope: Text
    status: SourceState
    observed_at: AwareDatetime | None
    result_count: Count | None
    failure_code: FailureCode | None

    @model_validator(mode="after")
    def valid_status(self) -> "SourceCoverage":
        if self.status == "not_attempted":
            if self.observed_at is not None or self.result_count is not None:
                raise ValueError("Unattempted source cannot claim observed results.")
        elif self.observed_at is None:
            raise ValueError("Attempted source requires observation time.")
        if self.status in ("success", "partial") and self.result_count is None:
            raise ValueError("Successful/partial source requires a known result count.")
        if self.status in ("failed", "partial") and self.failure_code is None:
            raise ValueError("Failed/partial source requires a bounded failure code.")
        if self.status == "failed" and self.result_count is not None:
            raise ValueError("Failed source count is unknown, not known empty.")
        if self.status == "success" and self.failure_code is not None:
            raise ValueError("Successful source cannot have a failure code.")
        return self


class OperationalDiagnostics(Contract):
    """No raw payloads, exception strings, credentials, personal IDs or prompts."""

    stage: Literal["collection", "semantic_analysis", "complementary_discovery"]
    model_id: Identifier | None
    cost_scope: Literal["model_tokens_only"] = "model_tokens_only"
    status: Literal["success", "partial", "fallback", "failed", "skipped"]
    attempts: Count
    input_count: Count
    result_count: Count
    latency_seconds: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None
    tool_calls: Count | None
    input_tokens: Count | None
    cached_input_tokens: Count | None
    output_tokens: Count | None
    total_tokens: Count | None
    estimated_model_cost_usd: Amount | None
    usage_complete: StrictBool
    failure_code: FailureCode | None

    @model_validator(mode="after")
    def valid_usage(self) -> "OperationalDiagnostics":
        if self.usage_complete and any(
            value is None
            for value in (
                self.input_tokens,
                self.cached_input_tokens,
                self.output_tokens,
                self.total_tokens,
            )
        ):
            raise ValueError("Complete usage requires all token counts.")
        if self.cached_input_tokens is not None and self.input_tokens is not None:
            if self.cached_input_tokens > self.input_tokens:
                raise ValueError("Cached input cannot exceed input tokens.")
        if (
            self.total_tokens is not None
            and self.input_tokens is not None
            and self.output_tokens is not None
        ):
            if self.total_tokens != self.input_tokens + self.output_tokens:
                raise ValueError("Token totals must agree.")
        return self


class FactualExclusion(Contract):
    source_id: Identifier
    source_record_id: Text
    reason: Literal[
        "outside_region",
        "outside_window",
        "invalid_time",
        "unresolved_location",
        "missing_evidence",
        "duplicate_occurrence",
    ]
    duplicate_of: Identifier | None

    @model_validator(mode="after")
    def valid_duplicate(self) -> "FactualExclusion":
        if (self.reason == "duplicate_occurrence") != (self.duplicate_of is not None):
            raise ValueError("Only duplicate exclusions require a retained occurrence reference.")
        return self


class RegionalWeekendUniverse(Contract):
    schema_version: Literal["1"] = "1"
    scope: ResearchScope
    opportunities: tuple[RegionalOpportunity, ...]
    sources: tuple[SourceCoverage, ...]
    exclusions: tuple[FactualExclusion, ...]
    diagnostics: tuple[OperationalDiagnostics, ...]
    unknowns: tuple[ImportantUnknown, ...]

    @model_validator(mode="after")
    def valid_universe(self) -> "RegionalWeekendUniverse":
        _validate_inventory(self.scope, self.opportunities)
        occurrence_ids = tuple(o.occurrence_id for p in self.opportunities for o in p.occurrences)
        _unique(occurrence_ids)
        _unique(tuple(s.source_id for s in self.sources))
        sources = {s.source_id: s for s in self.sources}
        for source in self.sources:
            if source.observed_at is not None and _instant(source.observed_at) > _instant(self.scope.as_of):
                raise ValueError("Source observation cannot follow as_of.")
        for opportunity in self.opportunities:
            for evidence in opportunity.evidence:
                if evidence.source_id not in sources or sources[evidence.source_id].status not in (
                    "success",
                    "partial",
                ):
                    raise ValueError("Evidence must reference a source with usable results.")
                if sources[evidence.source_id].result_count == 0:
                    raise ValueError("Known-empty source cannot supply opportunity evidence.")
                if _instant(evidence.observed_at) > _instant(self.scope.as_of):
                    raise ValueError("Evidence observation cannot follow as_of.")
        for exclusion in self.exclusions:
            if exclusion.source_id not in sources:
                raise ValueError("Exclusion references an unknown source.")
            if exclusion.duplicate_of is not None and exclusion.duplicate_of not in occurrence_ids:
                raise ValueError("Duplicate exclusion must reference a retained occurrence.")
        return self


class RegionalAnalysisRequest(Contract):
    """Future AI #1 input; no adapter or provider execution in WP1."""

    scope: ResearchScope
    opportunities: tuple[RegionalOpportunity, ...]

    @model_validator(mode="after")
    def valid_inventory(self) -> "RegionalAnalysisRequest":
        _validate_inventory(self.scope, self.opportunities)
        return self


class RegionalDiscoveryRequest(Contract):
    """Future AI #2 input; existing inventory is evidence, never user policy."""

    scope: ResearchScope
    existing_opportunities: tuple[RegionalOpportunity, ...]

    @model_validator(mode="after")
    def valid_inventory(self) -> "RegionalDiscoveryRequest":
        _validate_inventory(self.scope, self.existing_opportunities)
        return self


def _validate_inventory(
    scope: ResearchScope, opportunities: tuple[RegionalOpportunity, ...]
) -> None:
    _unique(tuple(o.opportunity_id for o in opportunities))
    _unique(tuple(o.occurrence_id for p in opportunities for o in p.occurrences))
    region = scope.region
    boundary = (region.country_code, region.subdivision_code, region.county)
    exact_occurrences: set[tuple[object, ...]] = set()
    for opportunity in opportunities:
        locations = [opportunity.location, *(o.location for o in opportunity.occurrences)]
        if any((p.country_code, p.subdivision_code, p.county) != boundary for p in locations):
            raise ValueError("Opportunity is outside the explicit regional boundary.")
        for evidence in opportunity.evidence:
            if _instant(evidence.observed_at) > _instant(scope.as_of):
                raise ValueError("Evidence observation cannot follow as_of.")
        for occurrence in opportunity.occurrences:
            if not scope.window.overlaps(occurrence.start, occurrence.end):
                raise ValueError("Occurrence does not overlap the regional weekend.")
            place = occurrence.location
            if place.city is not None and place.venue is not None:
                signature = (
                    opportunity.title,
                    occurrence.start.astimezone(UTC),
                    _instant(occurrence.end) if occurrence.end is not None else None,
                    place.country_code,
                    place.subdivision_code,
                    place.county,
                    place.city,
                    place.venue,
                )
                if signature in exact_occurrences:
                    raise ValueError("Exact duplicate occurrences must combine provenance.")
                exact_occurrences.add(signature)


def _unique(values: tuple[str, ...]) -> None:
    if len(values) != len(set(values)):
        raise ValueError("Identifiers and claim references must be unique.")
