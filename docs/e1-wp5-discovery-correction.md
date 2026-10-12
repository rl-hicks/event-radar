# E1 WP5 corrective implementation: failure evidence and accounting

Starting HEAD: `2eae450467c7ec5c53d11031a19bff034d45b23b`.
Branch: `e1/shared-regional-intelligence`; PR #2 remains draft.
Scope: offline implementation and deterministic verification only. WP7 remains open;
this document is implementation evidence, not a governing acceptance artifact.

## Historical evidence and its limits

The execution lead's handoffs report failed runs
`ba52478e-1b92-4f6a-a0d8-98c0eba82761` and
`12b19362-4705-46b3-a98b-39acb5562e0c`, followed by partial run
`c3d5a136-7906-4a06-af44-9fbd3b2239d3` and snapshot
`97ee0f71-0cab-4e23-98c2-76d24100a8f1`. That snapshot was reportedly read back
successfully and held 106 opportunities (81 events, 25 hikes), with successful WP4
enrichment and WP5 planning followed by research `invalid_response`.

These are historical reported results, not independently reverified records.
The stopped historical PostgreSQL container used tmpfs with no persistent mount.
The execution lead acknowledged loss of that development evidence and authorized
continuing offline. The container was not restarted, recreated, reset, or modified.
No known evidence export exists; no unrelated directories or private state were
searched, and no historical records were reconstructed or inserted anywhere.

The historical WP5 cause is **not conclusively diagnosable**. The old adapter used
one code for incomplete responses, explicit response errors, missing parsed output,
and no detected web-search calls. Some SDK errors could also escape that boundary.
Reported zero search calls therefore cannot establish that no searches were billed.
The prior `no_incremental_candidates` stop reason resulted from checking yield before
wave failure; it is not evidence that research completed normally.

## Bounded diagnostic contract

Existing shared `FailureCode` values remain unchanged. Existing `FailureCategory`
values are reused, with one additive category, `tool_behavior`. No competing failure
taxonomy is introduced. A finite discovery-specific reason refines a category:

| Boundary | Category / reason examples |
| --- | --- |
| Transport or HTTP timeout | `provider_transport` or `timeout` / `request_failed` |
| HTTP status, including 429 | `provider_status` / `request_failed`; existing `rate_limited` code |
| Request schema construction | `configuration` / `schema_construction`, zero requests |
| SDK structured JSON/Pydantic parsing | `sdk_parse` / `sdk_parse` |
| Response envelope validation | `response_schema` / `response_schema` |
| Defensive SDK finish-reason handling | `sdk_finish_reason` |
| Incomplete / explicit error / other non-completed response | `response_behavior` / distinct bounded reasons |
| Missing structured output | `response_behavior` / `missing_structured_output` |
| Required search absent / failed / not established | `tool_behavior` / distinct bounded reasons |
| Research/verification result mapping | `local_validation` / `local_result_invalid` |
| Verified-candidate materialization | `local_validation` / `materialization_invalid` |
| Unexpected local exception | shared classifier: `local_invariant`, `local_validation`, timeout, or cancellation |

`AdaptiveDiscoverySummary.operations` records ordered planning, research, verification,
local-validation and materialization evidence. A local ordinal identifies research
tasks; diagnostic records do not copy model-generated task names or search text.
Separate fields record whether an HTTP response was received, the bounded response
state, structured-output acceptance, and required-search evidence. Multiple facts
survive together: malformed structured output can coexist with an observed search
or with an absent search. An HTTP error response is not a completed model response.

Only finite enums, booleans, numbers and local ordinals enter these new diagnostics.
No raw response, exception message/class name, prompt, request, credential, provider
request identifier or arbitrary error code is stored. Existing source-lead output
and wave task identifiers remain the pre-existing public research contracts.

## SDK behavior and accounting

Installed and locked SDK reviewed: OpenAI Python **2.53.0**. The implementation calls
the supported `responses.with_raw_response.parse(...)`, reads numeric response
telemetry through the public HTTP response, then calls its public `parse()` method.
This defers structured-output parsing until safe telemetry is available. No private
SDK helper is called. The raw body exists transiently inside the adapter and is never
persisted or logged. The existing model, prompts, reasoning settings, web-search
configuration, `tool_choice="required"`, `max_tool_calls`, and `store=False` remain.
Injected clients also receive `max_retries=0` through public `with_options`, preventing
hidden retries from bypassing the discovery call budget.

Each operation retains known input/cache/output/total tokens, model-token cost,
latency and observed search-call count. Missing values remain null. Model completion
counts are distinct from attempts and HTTP receipt. In-flight fatal failures retain
prior operation telemetry and mark attempt accounting incomplete. Known totals are
subtotals, not claims about an unobserved bill. An unknown request may have incurred
model and tool charges. `web_search_calls_complete` and `model_cost_complete` make
that limitation explicit; web-search fees are not included in model-token estimates.
Cache details missing from the provider remain unknown; the existing pricing helper
can estimate without a cache discount, but completeness is false.

Discovery stops after a provider failure rather than attempting sibling tasks or
verification with uncertain remaining spend. `provider_failure` takes precedence
over zero incremental yield. Successful duplicate-only/empty waves retain
`no_incremental_candidates`. Known call/search/cost caps remain enforced; unknown
model-cost accounting also prevents another provider call. This does not turn the
existing post-response cost ceiling into a hard prepaid monetary cap: one request's
actual cost may exceed the remaining estimate before its response is available.

Expected optional provider failures still yield partial/fallback shared results.
Unexpected local errors and cancellation retain the worker's fatal behavior, with
safe diagnostic callbacks preserving prior usage and stage evidence. PostgreSQL JSON
contracts accept the added fields; older summaries default to no operation evidence
and unknown completion/tool-accounting completeness. No migration or claim/concurrency
behavior was changed.

## Offline verification

Tests use synthetic records, `httpx.MockTransport`, and deterministic provider fakes.
The SDK test module blocks socket connections. Full Python/database verification runs
inside the network namespace of a new, separately named PostgreSQL 17 container,
`event-radar-wp5-corrective-tests`, started with `--network none`, no published ports,
and its own disposable data storage. Existing localhost/55432 test safety guards
remain unchanged. The historical container is excluded from all test operations.

Coverage includes valid planning/research/verification; missing, malformed and
schema-invalid structured output; incomplete and explicit-error responses; absent,
failed and unobservable required searches; transport/timeout/status failures;
response-validation and pre-request schema errors; partial/absent usage; local result
validation/materialization; cancellation and unexpected local errors; budget limits,
overruns, failure precedence, and backward-compatible summary reads.

Persistence tests cover each provider stage with and without a prior successful
snapshot, safe diagnostics in run and snapshot JSON, retention of the collected and
semantically enriched universe, null unknowns, failed-refresh last-good preservation,
and absence of raw-content sentinels/private payload fields. Existing real PostgreSQL
migration, identity/auth, same-key replay/concurrency, distinct-key, process-death and
two-reader reuse tests remain required. Local final verification: **650 Python passes**, one expected opt-in hosted Supabase
skip, including **76 focused discovery/worker passes** and all required PostgreSQL tests.
Web verification: **39 passes**, ESLint, TypeScript and production build. Ruff format/lint,
strict mypy (84 source files), source/artifact security checks, diff whitespace, CLI help
and Alembic metadata checks pass. Locked Python sync and Node 24 installation were
verified offline. Existing Starlette HTTP-client deprecation and SQLAlchemy cyclic-FK
metadata warnings remain. The final response records the commit SHA and observed CI result; an earlier CI run is not treated as this patch's CI.

## WP8 quality review: source-supported findings only

No matching public fixtures for the named events were found under repository fixtures,
data or existing documentation. Without the lost historical records, none of these
examples can be conclusively classified as a genuine duplicate, a separate occurrence,
or a specific normalization defect.

| Reported example | Established from repository code | Inference and unresolved evidence; WP8 disposition |
| --- | --- | --- |
| Museum of Sonoma County Block Party | Shared deduplication requires equal normalized title, exact UTC start and city; populated venues/end times must agree. | A wording, venue, end-time or start-time difference can retain likely duplicates. Exact historical pair unavailable; genuine duplicate vs separate occurrence unresolved. |
| Haunts & Handiwork | Unicode/case/punctuation normalization is applied, but title synonyms and wording changes are not reconciled. | Title resemblance alone is insufficient. Candidate identity/provenance review needed; defer merging or discarding. |
| Cotati Oktoberfest, noon vs 1 p.m. | Different starts prevent a merge, and identities include source record/start time. | The reported pair suggests a possible source conflict; separate sessions or normalization error cannot be excluded. No preferred start established. |
| Celestial Sips, stored 5 p.m. vs description 6 p.m. | Happening Sonoma takes `utc_start_date` as UTC and preserves description separately; it does not reconcile textual times. | Possible structured-source/prose conflict, stale description, or parsing/timezone issue. No historical record permits attribution or a time correction. |
| River Run, stored 8 a.m. vs description 3 p.m. | Same structured-time/prose separation; the shared adapter copies event time into occurrence and evidence and copies description into the evidence summary. | Seven hours is compatible with an October Pacific/UTC interpretation error, but is not proof of one. Source field and raw observation unavailable; unresolved time ambiguity. |

Relevant paths: `collectors/sonoma_county.py` constructs a Pacific timestamp from
calendar date and displayed list time; `collectors/happening_sonoma.py` explicitly
parses UTC fields; `shared/event_sources.py` preserves source/record/URL and extracted
time; `shared/deduplication.py` uses conservative occurrence equality and retains
alternate evidence when it merges. These are established code behaviors, not proof
of the historical source inputs. Time evidence currently repeats the extracted value;
it is not an independent cross-check against prose. Cross-record time disagreement
can remain separate records without a structured conflict marker.

WP8 should review future retained public source records and source timestamps before
adopting a conflict policy. No collector, normalization, identity, deduplication,
event time, source roster or personalization changes are included here.

## Separate operational follow-up

Before another authorized real development proof, establish durable public-only
evidence export or persistent development PostgreSQL storage, with a retention and
readback check independent of container lifetime. Keep disposable migration-test
storage separate from development evidence. No hosted storage, migration, deployment,
recurring schedule or real research execution is authorized or implemented here.
