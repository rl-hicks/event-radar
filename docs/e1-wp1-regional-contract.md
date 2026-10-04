# WP1 — neutral regional research contract

Status: implemented for independent E1 Lead review; no WP2 execution authorized.
Authority: the supplied WP1 execution packet, incorporating Engineering Phase Map
v1.1. External governing documents were not independently opened. This document
does not revise those artifacts. WP0 is accepted and closed.

Base: `3a0fb5e9ff414ecd14d923d23551e07977d287a1`.
Implementation: `src/event_radar/models/regional.py`.
Fixtures: `tests/fixtures/regional/`.
Tests: `tests/test_regional_contract.py`, `tests/test_regional_isolation.py`.

## 1. Scope and boundaries

This package implements typed, JSON-serializable contracts, deterministic validation,
and evidence fixtures. It does not invoke collectors or AI, adapt the legacy pipeline,
persist research, migrate databases, schedule jobs, or produce personalized outputs.
No existing models, prompts, tests, API routes, workflows or runtime configuration change.

Neutral research describes experiences, participation, interactions, factual logistics,
source-supported characteristics, uncertainties and provenance. It makes no attendance
recommendation, personal score, personal fit/disposition, or schedule-fit verdict.
A profile is neither required nor accepted, even as an empty object.

The original personal Thursday schedule remains disabled. Keeping old personal
outputs identical is not an E1 acceptance requirement; their tests are nevertheless
preserved during this package.

## 2. Actual legacy field classification

Categories: **F** source fact; **S** supported regional semantic description;
**D** dynamic/uncertain fact; **P** personal policy/verdict; **O** operational.
A classification as S does not certify the existing value as neutral. Existing AI
values produced under personal prompts must be regenerated/reviewed in later WPs,
not blindly copied into the new contract.

| Inspected legacy contract / fields | Class | Regional treatment |
| --- | --- | --- |
| Event: source_name, source_id, source_url, alternate_sources | F | Preserve each source and record reference as evidence; never discard alternatives when deduplicating. |
| Event: title, description, start_time, end_time, venue, city, state, categories | F/D | Preserve supported values; aware times, explicit location and time evidence; null is unknown. Source categories are not taste weights. |
| Event: price_min/max/currency/details, price_conflict; is_free() | F/D | Explicit unknown/known/conflicting price with source-linked alternative quotes. Zero is known free only when supported; no collapse of a conflict to free. |
| EventOccurrenceFact: event_id and sources, remaining occurrence facts | F/O | Stable caller-assigned occurrence IDs; source identity is separate. Existing legacy hash includes source_name/source_id and is not adopted as canonical regional identity. |
| EventSourceFact / WebEvidenceSource: URLs, supported_claims, confidence, summary, extracted occurrence times | F/D | Claim-specific evidence, observation/publication timestamps, reliability and exact extracted-time validation. |
| WeekendEventCard: candidate_type/id, origin, title, occurrences | F/O | Event/hike kinds and IDs, explicit alternatives, source coverage channels; no preferred-source identity. |
| WeekendEventCard / ScrapedEventJudgment: experience_summary, experience_modes, interaction_architecture | S | New evidence-linked experience/participation/interaction/setting descriptors. No automatic legacy-value migration. |
| WeekendEventCard / judgment: solo_viability, active_value, distinctiveness, social_opportunity | P/S | Do not carry legacy verdict fields. A supported participation or interaction description may be separately represented, without ranking personal value or inferring who will attend. |
| WeekendEventCard / judgment: friction_summary, schedule_observation | P/D | Drop fit verdicts. Source-supported logistics can become descriptors; no home-relative drive assessment or personal calendar. |
| ScrapedEventJudgment: disposition, reason_for_disposition | P | Excluded. Factual exclusions have a closed reason set, not retain/borderline/reject taste decisions. |
| ScrapedEventJudgment: experience_group_id; ExperienceGroupProposal: group_id, occurrence_ids, experience_summary | F/S/O | Opportunity groups explicit occurrence alternatives with unique IDs and evidence. Grouping implementation remains later work. |
| WeekendEventCard: uncertainties, source_confidence, verification_confidence, semantic_analysis_available | D/O | Typed unknowns and evidence/descriptor confidence. semantics=null means unestablished; [] means assessed with no supported descriptors. No invented fallback semantics. |
| ScrapedEventAnalysisRequest / WebDiscoveryRequest: generated_at, weekend_start/end | O/F | Explicit as_of and a full Friday-to-Monday local calendar window, never truncated by current time. |
| Both requests: user_context, personal_experience_context, permanent_directions, temporary_directions | P | Entirely absent from both regional request schemas; extra fields fail validation. |
| StructuredRuntimeContext: profile_id/label, base_location, drive_tolerance, cost_tolerance, hiking_posture, recurring_availability | P | Despite the legacy 'runtime' label, all are personal and excluded. Region configuration replaces user geography, not a synthetic user. |
| ExistingEventIdentity: title/start_time/city/venue/source_urls; request events/existing_events | F | Regional request inventory carries explicit opportunities/occurrences/evidence. Empty discovery inventory is valid. |
| DiscoveredEvent: discovery_id, title, evidence_sources, start/end, venue/city/state, description_evidence, price fields | F/D | Preserve evidence-backed factual counterparts and unknowns; no minimum opportunity count. |
| DiscoveredEvent: why_it_may_fit and other card verdicts | P | Excluded; supported descriptive content uses the same evidence-linked descriptor schema as scraped research. |
| WebDiscoveryResult: discoveries max_length=12 | P/O | No regional output cap. Future provider budgets must be explicit operational constraints and report incomplete coverage, not silently discard eligible inventory. |
| Hike: id/name/park_or_area/managing_agency/region/nearest_city; trailhead and coordinates; official/secondary URLs | F | Title, administrative location, route description and source evidence. Dedicated coordinate/agency fields are not needed for WP1; future expansion must preserve provenance. |
| Hike: distance/elevation/duration, route_type/start/end/trail_sequence, difficulty | F/S | Explicit distance/elevation and evidence-linked route description; difficulty/effort describes the route, never user fitness suitability. No guessed schedule. |
| Hike: setting/shade/exposure/sensitivity attributes and experience_tags | F/S/D | Supported setting/participation/logistics descriptors; not scores. Numerical weather/route extensions can be added when a later consumer requires them. |
| Hike: preferred/acceptable/poor_months, best_time_of_day, minimum_reasonable_daylight_minutes | S/P/D | Require separating evidence from policy before reuse; no current eligibility rule inferred from them. |
| Hike: solo_fit, scenic_value, drive_friction_from_santa_rosa | P | No fit/scenic score or Santa Rosa-relative travel restriction. Evidence may describe scenery without ranking desirability. |
| Hike: parking/access_baseline/seasonal_access/important_route_notes, dynamic_status_check_required | F/D | Baseline notes are evidence/descriptors, not proof of current openness. access_open explicitly unknown/true/false with access evidence. |
| Hike: provenance, data_quality; catalog version/cutoff, units | F/D/O | Preserve evidence confidence, observation time and route units. No need to import the legacy catalog/model in WP1. |
| HikeWindowWeather / HikeWeatherContext / BaselineWeatherContext | D | Forecasts are time/location-dependent, not permanent route facts. WP1 records unavailable weather explicitly; a full forecast contract is deferred. |
| HikeWindow/DayEvaluation: eligible, score, reasons, cautions, exclusion_reasons, best_window | P/D | Do not transplant eligibility/ranking. Preserve sourced hazard/uncertainty descriptions without personalized thresholds. |
| HikeCandidate: hike, best_day/window, score/reasons/cautions, alternate_day_evaluations, access | F/P/D | Regional independent hike contains route and access evidence; no selected 'best' personal day/window or shortlist score. Organized/guided hikes are scheduled events. |
| HikeCandidateSelection: candidates/day_evaluations, weather counts, derived viable/infeasible counts | P/O | No ranked candidate cap. Source status and bounded diagnostics replace selection summary as research evidence. |
| RecommendationContext: user_context, personal context, direction lists | P | No regional counterpart. |
| RecommendationContext: generated_at/weekend, baseline_weather, event_cards/hike_candidates, known_unknowns, pipeline notes | F/D/O | Neutral scope, opportunities, typed unknowns, explicit source status. Raw pipeline note/error strings do not enter operational diagnostics. |
| HikeCandidateContext: solo_fit, drive_friction, deterministic_score/reasons, chosen day/start/finish | P | Excluded. Physical route data and access uncertainty are retained separately. |
| ImportantUnknown: price/access/weather/availability and other source gaps | D | Preserve explicit supported gaps. No private demographic inference or personalized travel computation. |
| CuratedOption roles/why_it_survived/tradeoffs/social/solo/friction/schedule observations; NearMiss; WeekendCuration quotas | P | Entire downstream personal contract is out of WP1 scope; no E2 replacement schema. |
| AIStageDiagnostics / batch outcomes: status, batch/attempt/result counts, fallback IDs, latency, tools, model | O | Closed stages/status/error codes, stable model identifier, numeric usage and model-token-only cost estimate. No raw provider errors/payloads/prompts. Per-batch execution remains later work. |
| TokenUsage: input/cached/output/total tokens, estimated_model_cost_usd | O | Independent types, null versus zero preserved, complete versus subtotal usage explicit; no Settings import or pricing calculation. |
| RecommendationScoringConfig / SCORING_SIGNALS | P/O | Category weights, minimum scores, free/evening boosts, child/professional exclusions, diversity and 28-item cap are not regional eligibility. Evidence-strength concepts can inform later supported interpretation. |
| HikeSuitabilityConfig | P/D/O | No 10-item cap, minimum score, scenery/season/time boosts or inherited weather thresholds. Actual forecasts/hazards remain useful evidence; concurrency is later operational configuration. |
| CurationConfig | P/O | No 10-hike/12-discovery/22-event/6-hike limits. Prompt size and reasoning settings are not regional eligibility rules. |

Inspected builders: `build_scraped_analysis_request`, `build_web_discovery_request`,
`event_occurrence_fact`, `build_recommendation_context`, `_hike_context`,
`event_candidate_id`, pipeline `_analysis_request` and `_factual_rejection_reasons`.
The legacy main/pipeline reads personal context before collection. All three prompts
declare personal context authoritative; AI #2 also uses user location in web_search,
and AI #3 embeds Saturday's personal climbing anchor. None are reused by WP1.

## 3. Wire contract and validation

All objects inherit a frozen Pydantic base with `extra="forbid"`; nested collections
are tuples (JSON arrays). Unknown fields are rejected, not silently stripped.
Public APIs are `model_validate_json`, `model_dump_json` and `model_json_schema`.
Decimal price/cost/distance values serialize as decimal strings. Aware datetimes are
ISO 8601 strings; comparisons use instants. Use full output including nulls for storage.

- Region: administrative country/subdivision/county boundary and IANA timezone.
- WeekendWindow: Friday date + timezone, deterministically derived start/end.
- ResearchScope: region, window, explicit as_of and research_policy_version.
- ResearchIdentity: region ID / Friday date / policy version, derived from scope.
- RegionalOpportunity: event or independent hike, title/location, evidence, supported
  semantics/categories, occurrences or route facts, current access and unknowns.
- Occurrence: aware start/end, location, evidence, price and availability.
- SourceEvidence: stable source/evidence IDs, public canonical URL, source record,
  claim types, extracted occurrence times, observed/published timestamps and confidence.
- Price: unknown with no quotes; known with one reconciled quote referencing all
  supporting evidence; conflicting with at least two distinct preserved quotes.
- Observation[T]: unknown requires null/no evidence; known requires value/evidence.
  Known false, zero and empty arrays are preserved. Null is never converted to false.
- SourceCoverage: channel, declared coverage description, source status/count/time
  and bounded failure code. Partial failure does not erase other source results.
- OperationalDiagnostics: bounded status and counters, optional model identifier,
  missing-aware telemetry and failure code. Cost scope is model tokens only.
- FactualExclusion: source record plus closed factual reason; duplicate_of must point
  to a retained occurrence. No arbitrary rejection prose or personal verdict.
- RegionalWeekendUniverse: versioned envelope over these objects.
- RegionalAnalysisRequest / RegionalDiscoveryRequest: only scope and neutral inventory.
  These are future input contracts, not live provider structured-output adapters.

Existence evidence is mandatory. Location, semantics, price, route and known access
must reference compatible claims. Occurrence starts must match extracted source times; known source ends cannot be discarded or contradicted, and a declared end requires end-time evidence;
a generic operator page cannot alone establish an occurrence. Sources referenced by
results must be successful/partial with nonzero counts. Physical access and
occurrence availability are distinct evidence claim types. Future observations are rejected
relative to as_of. Reliability is evidence confidence, not a claim of verified truth.

Important limits: validation enforces declared evidence relationships, not whether a
webpage truly supports a claim. Free descriptive text cannot be proven neutral or
secret-free by a schema. Only public inputs may be ingested; WP4/WP5 require neutral
prompt/output review. Never log raw validation payloads or `errors()` input values.
Diagnostic contracts accept no raw provider message field. Pydantic's trusted
`model_construct` and `model_copy(update=...)` bypass validation and are not ingress APIs.

Evidence URLs are canonical HTTPS citations on public DNS hostnames, without
credentials, fragments or nonstandard ports. IP literals, single-label names,
known local/reserved suffixes and numeric-only hosts are rejected. A bounded
allowlist preserves up to four nonduplicated, nonempty identifying selectors:
`event`, `event_id`, `eventid`, `eid`, `id`, `listing_id`, `occurrence_id`,
`post_id`, `p`, and `slug`; values are short alphanumeric/`._~-` identifiers.
Unknown, sensitive, tracking and malformed queries are rejected, not silently
stripped. The existing Sonoma County and Happenings collection endpoints are HTTPS,
but extracted detail links must be checked independently; adapters must
provide a safe equivalent canonical URL if their raw URL is rejected. This syntax-only contract does not resolve DNS,
follow redirects, verify actual public routability, scan arbitrary path text for
secrets, or guarantee that an allowlisted identifier is not sensitive. Later
network-fetch boundaries need separate DNS/IP/redirect protections.

## 4. Region, time and logical identity — proposed for Lead acceptance

Initial region is closed to exactly `sonoma-county-ca`, US / CA / Sonoma County,
`America/Los_Angeles` by its field types, preventing identity aliasing. Adding a
new region needs a later explicitly reviewed contract change. Sonoma County is the actual boundary; 'North Bay' in project
orientation does not silently widen this initial scope. No home coordinate/radius exists.

Weekend is Friday 00:00 inclusive through Monday 00:00 exclusive in regional local
time. Calendar arithmetic gives 71/72/73 elapsed hours across DST weekends. An event
with a supported end is eligible if its interval overlaps the weekend, including an
overnight Thursday event extending into Friday. Without an end, its start must fall
inside the window; no duration is invented. This overlap rule is a WP1 design proposal,
different from the legacy start-only rule, and awaits Lead acceptance.

as_of is an explicit knowledge cutoff for this assembled snapshot/request: all included
observations must be at or before it, comparing actual UTC instants (also across
ambiguous local DST hours). It need not be inside the weekend. Producers must
choose/update the cutoff explicitly after collecting the included evidence; no call to
now() exists. No arbitrary freshness TTL is imposed: observed_at, published_at and
confidence allow later stale-evidence policy without falsely declaring access current.

Logical identity is the exact tuple (region_id, Friday local date, research_policy_version).
Example: `sonoma-county-ca/2026-10-02/regional-v1`. The slash-delimited key is an accessor,
not a second editable JSON field; the serialized scope contains all inputs.
as_of, source order, model usage, retry count and request time do not change identity.
A substantive boundary/timezone/inclusion-policy change requires a policy-version bump
(or a new region ID). Schema version and research policy version have different purposes.

Opportunity/occurrence IDs are explicit producer-owned identifiers, independent of
preferred source and research timestamp. WP1 validates uniqueness, not a durable ID
allocation algorithm. Exact fully located duplicates must combine evidence. Distinct
occurrence times survive as alternatives; unknown venues are not guessed to be equal.
No fuzzy merging, automatic source priority or cross-run identity reconciliation is added.

Later persistence must distinguish this logical research key from attempt/snapshot IDs,
use durable uniqueness/transaction rules and define replacement/history semantics.
WP1's key is a prerequisite, not proof of durable idempotency or a weekly job.

## 5. Factual inclusion and breadth

An event needs existence, supported time overlapping the window and evidenced location
inside the declared county. An independent hike needs existence, in-boundary location
and route evidence; it has no invented scheduled occurrence. Location uncertainty is
unresolved_location, not an inferred county. Boundary validation uses declared
administrative fields, not geocoding; producers must verify them from public evidence.

Missing price, forecast, access verification, availability or semantic enrichment does
not remove an otherwise factual opportunity. Confirmed closed/unavailable status remains
a factual false value, not a recommendation or automatic deletion. Specific safety and
freshness exclusion policy is not silently imported from personal suitability settings.

There are no travel-radius, fitness, age/category taste, scenic, minimum-score, diversity,
shortlist or minimum-output rules. A twelve-mile synthetic route remains in the fixture
alongside a workshop regardless of the eventual consumer's preferences. A completely
empty universe and zero complementary discoveries are valid. Failed/unattempted sources
have unknown counts; successful zero is a known-empty source result, never proof that
the entire region has no opportunities. Coverage scope must state what was searched.

Factual exclusions are limited to outside_region, outside_window, invalid_time,
unresolved_location, missing_evidence and duplicate_occurrence. They preserve source
record traceability. Adapters that produce these records and conservative deduplication
execution are later packages; WP1 does not filter a live feed.

## 6. Tests, evidence and acceptance limits

Synthetic fixtures use example.org URLs, fabricated event/route details, conflicting
prices, multiple sources, unknown access, partial calendar failure, unavailable weather
and a successful empty complementary search. Two intentionally different consumer
profiles exist only as test data, with no production profile schema or curation function.

Tests prove JSON roundtrip preservation, nested extra-field rejection, exact duplicate
handling, occurrence alternatives, factual/evidence boundary validation, DST and exclusive
window boundaries, timestamp-independent identity, no personal caps, empty results,
missing/zero telemetry and shared serialized reuse by both consumers. That last proof is
contract reuse, not an assertion that regional AI is already neutral or E2 is implemented.

A fresh subprocess blocks all legacy models, settings, research/services, providers,
database/API imports, private/provider path access, sockets, subprocesses and writes.
It constructs and roundtrips the populated universe and generates schemas in an empty
working directory with no inherited credentials and a poisoned synthetic legacy setting.
Existing E0 API-isolation and security tests remain unchanged.

Observed WP1 verification (local, clean inherited environment):
- Ruff format check: 117 files already formatted; lint passed.
- mypy: no issues in 64 source files.
- Full pytest: 413 passed, 6 skipped, one existing Starlette/httpx deprecation warning.
  The 59 new WP1 tests all passed; existing API-isolation and security tests passed.
- Skips: five disposable-PostgreSQL tests (no TEST_DATABASE_URL) and one opt-in real
  Supabase test (no staging credentials). No tests were suppressed or modified.
- Source security scan: 157 staged/tracked files passed; staged whitespace check passed.
- Web, dependency locks, Alembic and workflows are byte-unchanged from the accepted base.
  Web checks were not unnecessarily rerun. The accepted baseline's 39 web passes,
  artifact scan and five live PostgreSQL passes remain historical baseline evidence,
  not a claim of a new WP1 CI run.
- Branch: codex/e1-wp1-regional-contract. Only six new WP1 files are changed.

Final commit identity and worktree status are recorded in the WP1 handoff.
No additional local Docker investigation or permission changes are necessary: WP0's
exact-base CI evidence already covers the five unchanged PostgreSQL tests.
Hosted deployment provenance remains unverified; tracked deployment configuration is
not evidence of a currently deployed commit.

## 7. Future test replacement candidates — no removals now

| Existing test family | Preserve | Later replacement candidate and rationale |
| --- | --- | --- |
| test_event_analysis*, test_web_event_discovery | Reference completeness, batching, failures, evidence/time checks, sanitization, telemetry | Personal request/projection equality, retain/borderline/reject semantics and why_it_may_fit; WP4/WP5 must test neutral descriptions instead. |
| test_event_evaluation, test_hike_suitability | Factual dates/weather/route handling and explicit uncertainty | Taste weights, personal category exclusions, best-window/scenic bonuses and shortlist counts must not define regional inclusion. |
| test_recommendation_context | Authoritative facts, provenance, unknown prices, recurring occurrence distinction, uncapped event inventory | Required profile/directions and capped/scored hike context are personal downstream contracts. |
| test_curation_rendering, test_audit | Truthful fallback, price conflicts, evidence chains, timezone rendering, no private leakage | Packet headings/attachment wording, personal context projections and audit artifact layout are not regional output acceptance. |
| test_personal_context, test_user_context | Retain legacy boundary protection while that path exists | Required personal sections/version and user policy are not shared worker prerequisites. |
| test_llm_curation, test_telegram, test_telegram_updates | Retain until separately authorized migration | Final personalized choices, owner delivery and direction clearing are outside shared research, not dependencies to inherit. |
| test_pipeline_degradation, test_model_usage | Independent source degradation, no masking programming errors, missing-aware accounting | Personal context assembly/output assertions can later move to the appropriate consumer boundary. |
| test_api_shell, test_security_baseline, auth/database tests | All current foundation boundaries | No WP1 replacement proposed. |

## 8. Decisions for independent acceptance

Accept or revise the proposed initial county/window/policy identity, interval-overlap
rule, evidence cutoff semantics, and public canonical-URL restriction before wiring
producers. No broader geography, hidden freshness thresholds or personal eligibility
rules have been assumed. None requires live provider access to review.

Not implemented: neutral AI #1/#2 execution, adapters/extraction, shared worker, migrations,
durable snapshots/idempotency, scheduling, caching, billing or personalization.
Stop at WP1.
