# E1 core coexistence technical note — WP8 evidence

Evidence baseline: accepted WP7 `8d27875df2dae2bdeae17b0c16732ce51e8cc69c`.
This is an engineering inspection note supporting the future E1 roadmap, not a
new governing artifact or implementation authorization. No shared worker, regional
schema, depersonalized prompt, or product capability is implemented here.

Inspection used tracked source, prompts, configuration examples, tests, and workflows.
No private context/state contents were read or copied. Reuse classifications below
are conditional engineering assessments, not proof of multi-user correctness.
Paths below are relative to the repository root; module rows under services/models
refer to `src/event_radar/`. Actual function names identify source evidence.

## 1. Verified research architecture and production entrypoints

`pyproject.toml` registers `event-radar = event_radar.main:main`.
`src/event_radar/main.py::main` parses arguments and calls
`asyncio.run(execute(...))`; its module guard calls main only when executed as a
module. Import does not call run, but imports legacy settings (see section 5).

Normal execution:

1. `execute()` calls `read_directions()` before `run()`. With configured Telegram
   owner credentials, it polls updates, accepts only authorized private-chat
   directions, writes direction files, and advances the update offset.
2. `run()` calls `_build_current_pipeline()`: Pacific current time, required JSON
   user context, required Markdown preference context, and permanent/temporary
   direction files enter the run here.
3. `services/pipeline.py::build_recommendation_pipeline()` derives the weekend,
   loads the hike catalog, and concurrently obtains both public event sources,
   regional baseline weather, and trailhead forecasts. Known provider failures
   degrade independently, with source-status diagnostics.
4. `deduplicate_events()` merges conservative cross-source occurrences;
   `_factual_rejection_reasons()` rejects unusable dates/location. The complete
   valid inventory goes to AI #1. `select_event_candidates()` runs as **legacy
   diagnostics only**, not the actual AI #1 input filter. Hike suitability selection
   remains an active candidate filter/ranker.
5. `build_event_intelligence()` runs AI #1 scraped analysis and AI #2 web discovery
   concurrently. It removes exact web duplicates against scraped inventory,
   constructs cards, removes candidate-ID collisions, and constructs final context.
6. `_curate_context()` calls AI #3 final curation through `curate_with_fallback()`.
7. Diagnostics aggregate source status, model tokens/cost estimates and latency.
   `render_chatgpt_packet()` produces Markdown; `write_chatgpt_packet()` writes it.
   `render_telegram_curation_summary()` creates the digest.
8. If delivery credentials exist, `deliver_weekend_digest()` sends message then
   document and only then clears temporary directions. Without them, output is
   printed and the packet still exists on disk. Delivery has no multi-user/idempotent
   transaction boundary: a partial send can occur before an exception.

`run_audit()` skips Telegram polling/delivery, but still calls the collection pipeline,
requires personal files and directions, and writes audit artifacts. `--audit --no-llm`
only disables AI calls. It is NOT an offline or side-effect-free smoke command.
`--help` exits during argument parsing, before execute.

`.github/workflows/event-radar.yml` is the weekly production boundary: Thursday
19:15 and 20:15 UTC schedules are filtered by the Pacific offset guard (12:15 local);
manual dispatch bypasses that schedule filter. Public application checkout explicitly
uses main. A separate private-state checkout is materialized before uv installation,
checks and `uv run event-radar`. Updated direction/offset files are copied back and
committed to the private repository. Concurrency is `event-radar-production` with
cancellation disabled. No schedule, checkout, secret, or delivery behavior changed.

## 2. Candidate reuse matrix

Import notation: **N** = inspected import graph has no private configuration read,
network request, or runtime-state write; ordinary Python/library imports still occur.
**S** = reaches legacy `config.settings = Settings()`, which may read `.env` and
validate process configuration at import time; no research/network call starts merely
from that import. Function execution side effects are separately listed.

| Source / entrypoints | Responsibility and dependencies | Reuse assessment / E1 conditions | Private context and I/O boundary |
| --- | --- | --- | --- |
| `collectors/sonoma_county.py`: `SonomaCountyCollector.collect`, `parse_sonoma_county_listing` | Sonoma Tourism monthly AJAX/HTML normalization to `models/event.py::Event`; httpx, BeautifulSoup, Pacific timezone | Conditionally reusable unchanged for this source/region. Retain source-specific parsing and date validation; not a generic geographic collector | N; HTTP only when collect is called; no personal-file reads |
| `collectors/happening_sonoma.py`: `HappeningSonomaCollector.collect`, `parse_happening_sonoma_event` | Paginated public events API; bounded retries/backoff; UTC query window; source evidence and price normalization | Conditionally reusable for this feed. Preserve pagination, error isolation, evidence and retry bounds | N; explicit collect performs HTTP; no personal context |
| `services/event_price.py::normalize_event_price`, `models/event.py` | Deterministic price parsing/conflict representation and normalized occurrence model | Candidate unchanged utility under existing input contracts. Keep unknown/conflicting prices explicit | N; values only |
| `services/event_deduplication.py::deduplicate_events` | Cross-source normalized title, exact start, city and compatible venue; chooses more complete primary record and preserves alternate provenance | Candidate unchanged conservative primitive. Not fuzzy entity resolution; same-source duplicates are not merged. Primary-source choice affects downstream IDs | N; values only |
| `services/weather.py`: `OpenMeteoWeatherClient.get_forecast`, `parse_open_meteo_forecast`, `forecast_dates_for_window`, `filter_weather_to_window` | Explicit location/date HTTP forecast, parsing and window slicing | Conditionally reusable with caller-owned location/window and provider failure policy; no regional cache exists | N; HTTP at get_forecast; no personal file |
| `services/hike_catalog.py::HikeCatalogRepository.load`, `models/hike.py` | JSON catalog read and validation, physical/trail/access attributes | Conditional local catalog adapter. Separate stable trail facts from Santa Rosa travel-friction annotations before regional reuse | N; file read only on load; tracked `data/hikes.json`, not private user state |
| `services/hike_weather.py::collect_trailhead_weather`, `weather_location_key` | Deduplicates forecast locations and bounds concurrent forecast requests through a protocol client | Conditional reusable weather collection seam with explicit timezone/config; no cross-run persistence | N; network via supplied client during call |
| `services/hike_suitability.py`: `evaluate_hike_day`, `build_hike_candidate_selection`, `select_hike_candidates` | Weather/daylight feasibility, candidate scores, best windows/day, diversity and caps; `hike_config.py` | Conditional. Weather feasibility is useful; score thresholds, seasonal/time/scenic bonuses and compression are policy, not neutral exhaustive inventory | N; supplied catalog/forecast objects only; active truncation can lose future-user options |
| `services/weekend.py::upcoming_weekend_window` | Remaining current or next Friday-through-Sunday interval from aware datetime | Conditional unchanged helper for that exact contract. Shared research must deliberately choose stable region/timezone/as-of/window semantics | N; no wall-clock read inside helper; main supplies Pacific now |
| `services/event_evaluation.py`: `evaluate_event`, `select_event_candidates` | Deterministic preference heuristics/caps from `recommendation_config.py` | Requires policy decision before shared reuse. Current pipeline uses result only for diagnostics; do not accidentally promote it to shared factual filtering | N; no private-file reads, but fixed taste/exclusion weights remain policy |
| `services/event_cards.py`: `event_occurrence_fact`, `validate_scraped_analysis`, card builders, `remove_exact_web_duplicates` | Bounded factual payloads, reference checks, grouping/cards and exact web overlap | Conditional utilities. Request builders embed personal policy; cards combine evidence with personal semantic judgments. Stable IDs are not a persistent regional schema | S transitively; functions use supplied user/direction/projection objects, not file loaders |
| `services/event_analysis.py`: `OpenAIEventAnalysisService.analyze`, `analyze_scraped_events_with_fallback` | Structured AI #1 responses, sequential bounded batches, reference validation, partial fallback and diagnostics | Requires future separation of factual analysis from personalized judgments/prompts. Transport/retry/reference/fallback machinery is reusable candidate code | S; constructor selects pricing but does not call OpenAI; analyze reads prompt and calls API with personal request |
| `services/web_event_discovery.py`: `OpenAIWebDiscoveryService.discover`, `discover_events_with_fallback` | AI #2 required web_search, evidence/date validation, bounded tool calls, duplicates and degraded outcomes | Requires discovery-policy separation. Tool location uses user's base city/timezone plus hardcoded California/US; current request is not region-only | S; prompt read and OpenAI/web tool at discover; personal structured/projection/direction data transmitted |
| `services/recommendation_context.py::build_recommendation_context`, `event_candidate_id` | Final context, unknowns, capped hike candidates, stable occurrence hash | Requires policy separation for context; hash utility conditionally reusable. Hash includes source identity as well as normalized facts; changes in preferred source may change ID | S transitively; personal fields supplied, no file reads in builder |
| `services/llm_curation.py`: `OpenAICurationService.curate`, `curate_with_fallback`, `validate_curation_references` | AI #3 retained options and near misses, reference/limit validation and fallback | Personal final-curation boundary, not shared research. Preserve fallback truthfulness; no multi-user generation implemented | S; prompt file + OpenAI at curate; full personal context serialized |
| `models/token_usage.py`: `parse_token_usage`, `aggregate_token_usage`, `ModelTokenPricing.from_settings` | Missing-aware usage and per-model cost estimates; `models/ai.py` and curation diagnostics depend on it | Math is reusable candidate code, but remove/avoid legacy import dependency in an approved E1 extraction. Costs exclude search fees/tier premiums; missing telemetry is not zero billing | S even when only importing the nominal model; runtime `Settings` import creates settings singleton |
| `services/curation_rendering.py`: render functions and `write_chatgpt_packet` | Personal Markdown packet and Telegram summary, explicit disk writer | Formatting helpers conditional; packet includes profile/home/availability and personalized choices. Not a public shared-research artifact | S transitively; rendering consumes private-derived context; writer creates directory and overwrites date-based file |
| `services/audit.py::write_audit_artifacts` | Detailed run inventory/decisions/context and packet artifacts | Personal diagnostic tool only until data-retention/redaction boundary is designed | S via pipeline/models; writes JSON/Markdown/CSV including private projections |
| `services/telegram.py`, `telegram_updates.py`, `direction_store.py` | HTTP delivery/polling, owner-command parsing, local JSON direction persistence | Operational adapters to retain in personal runtime. Shared worker must not call them; pure parsing helpers are not a worker contract | N on import; network and private state operations occur on explicit calls |
| `services/pipeline.py` and `main.py` orchestration | Wires all above into one personal run | Requires future orchestration/config separation before shared reuse. Useful existing seams are explicit inputs and separate collection/intelligence/curation/delivery stages | S; main execution loads private files, invokes providers, writes output and optionally delivers |

## 3. Concrete single-user coupling categories

These categories describe current dependencies, not an implemented future architecture.

- **Shared research extraction dependency:** fixed Sonoma feed endpoints; source-specific
  date normalization; AI #1 request/judgment semantics; AI #2 complementary discovery
  inventory and personal search posture; evidence/card schemas; source-dependent IDs;
  hike candidate truncation before final context. Deleting only final personalization
  would not yield a neutral complete inventory.
- **Personal-policy dependency:** `UserContext` drive/cost bands, base location,
  hiking posture and recurring availability; projected private Markdown; permanent
  and temporary directions; `RecommendationScoringConfig`, `HikeSuitabilityConfig`
  and `CurationConfig` limits. StructuredRuntimeContext omits old category/social
  taste fields but still contains profile identity and private operational policy.
- **Geography (shared extraction + personal policy):** tracked Settings default baseline
  weather to Santa Rosa. Hike model/catalog explicitly use
  `drive_friction_from_santa_rosa`; discovery prompt targets Santa Rosa/Sonoma/North
  Bay. AI #2 uses the supplied base city and timezone. No Rohnert Park literal was
  found in tracked src/config/prompts. A private user base may differ, but its actual
  value was deliberately not inspected; do not assert Rohnert Park is a code default.
  There is no active routing/travel-time service; context flags that unknown.
- **Window (shared extraction + personal policy):** weekend helper truncates an ongoing
  weekend at generated_at, and main uses Pacific now. A rerun can have a different
  inventory window. `prompts/weekend_curation.md` explicitly includes Friday open,
  Saturday morning-through-noon soft climbing anchor, Saturday later open, Sunday
  open, with direction overrides. That personal schedule survives even if JSON
  inputs are replaced.
- **Runtime/operational dependency:** `.env` singleton, cwd-relative paths, model
  configuration/pricing, private checkout materialization, direction JSON files,
  no per-user state partition/locking, single weekly owner invocation.
- **Output/delivery dependency:** one configured Telegram owner/chat; named packet
  output per weekend; audit artifacts with private context; temporary directions
  clear after successful two-part delivery. Shared retries cannot inherit these
  semantics without duplicate delivery/data collision risks.

## 4. Prompt/context coupling: all three AI stages

`PersonalExperienceContextRepository.load()` validates the required Markdown title,
semantic headings and supported version (unmarked documents default to version 1).
`PersonalExperienceContext.projection()` gives selected semantic sections to AI #1
and #2; AI #3 receives canonical full Markdown. This is deterministic projection,
not anonymization or depersonalization.

`pipeline._analysis_request()` calls `build_scraped_analysis_request()` with
`structured_runtime_context(user_context)`, AI #1 projection, and both direction
lists. AI #1 serializes this entire request to Responses structured parsing.
Batch copies replace only the event list, retaining the personal policy in each batch.

`build_web_discovery_request()` inherits structured user context and both direction
lists and receives the AI #2 projection, alongside existing-event identities. AI #2
sends the request to OpenAI and configures web_search using the user's location.

`build_recommendation_context()` combines cards/hikes/weather/known unknowns with
structured user context, full AI #3 preference context and directions. AI #3 then
serializes it. Therefore final personalization occurs here **and earlier** in
analysis/discovery/hike compression, not just at the rendering step.

Tracked prompts `prompts/event_analysis.md`, `prompts/web_event_discovery.md`, and
`prompts/weekend_curation.md` treat personal_experience_context as authoritative
policy. `store=False` on OpenAI calls does not mean private context is not transmitted.
Model defaults/override resolution are preserved: AI #1/#3 use stage override or
OPENAI_MODEL (default gpt-5.6); AI #2 defaults to gpt-6.1-sol, with explicit blank
falling back to OPENAI_MODEL. This note makes no live model/provider availability claim.

## 5. Private-state and environment boundary

| Path/config | When accessed | Read/write and assumptions |
| --- | --- | --- |
| `.env` and process variables | Import of `config.py` constructs Settings | Reads if present; malformed legacy env can fail import. OpenAI/Telegram secrets, weather, model/pricing, prompt/context/output paths live here |
| `config/user_context.json` (USER_CONTEXT_PATH) | `_build_current_pipeline` calls UserContextRepository.load | Required JSON, Pydantic validation; absent/invalid fails. Validation error text can include input data, so do not expose legacy errors through a public API |
| `config/personal_experience_preference_context.md` (PERSONAL_EXPERIENCE_CONTEXT_PATH) | Same execution stage, repository.load | Required Markdown/version/headings; no default public policy substitution |
| `state/telegram_offset.json` | read_directions with configured owner credentials; then save_offset | Required next_offset; read/write, no DB transaction or multi-worker lock |
| `state/permanent_directions.json`, `state/temporary_directions.json` | read_directions writes; `_build_current_pipeline` reads regardless of Telegram being enabled | Required files, lists of validated Directions; no user namespace. Temporary file reset after delivery |
| `data/hikes.json` (HIKE_CATALOG_PATH) | HikeCatalogRepository.load during pipeline | Tracked curated catalog read; distinct from private user context |
| `prompts/*.md` (stage-specific prompt paths) | analyze/discover/curate, not service constructor | Tracked policy instructions read when executing AI |
| `output/event-radar-<weekend-start-date>.md` (CURATION_OUTPUT_DIR) | run after curation | mkdir/write even without Telegram; same-date runs overwrite |
| `audit/` | write_audit_artifacts during audit | Generated context, private AI projection Markdown, final packet and diagnostics; not safe public regression fixtures |

Production workflow checks out `rl-hicks/event-radar-state` to `.private-state`,
requires the five private config/state files, materializes directories with mode 700
and files with mode 600, then persists the three state files back. Secret names are
EVENT_RADAR_STATE_TOKEN, OPENAI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID and
TELEGRAM_OWNER_USER_ID. No secret values were inspected.

Root `.gitignore` excludes `.env`/overrides (except examples), the two personal config
files, `.private-state/`, state JSON, output and audit. Ignore rules protect Git;
they do not make in-memory requests/artifacts public-safe. The public API does not
load these paths. The existing untracked web/.gitignore is preserved separately.

## 6. Import-time versus execution-time boundary

A subtle transitive dependency matters for E1:

`models.curation -> models.event_analysis -> models.ai -> models.token_usage -> config`

The same tail is reached by event_cards, recommendation_context, curation_rendering,
web_discovery models, AI services, audit and pipeline. Importing `Settings` solely
for a type annotation still executes config's module-level singleton. Dependency
injection of an AI client/pricing does not remove that import-time `.env` read.

Inspection found no automatic HTTP/research/Telegram execution at module import.
That is a narrower statement than claiming these modules are environment-pure.
Personal file repositories and direction-store functions defer reads/writes until
called. Collectors/weather defer HTTP; AI methods defer prompt reading/client calls.
Avoid importing main/pipeline/cards/AI diagnostic models into a prospective shared
worker until this configuration dependency is deliberately addressed or constrained.
No such refactor is necessary for the current API, which already excludes this graph.

## 7. Worker entrypoint analysis (not an implementation)

The current weekly worker is `main.execute`, invoked by the personal workflow.
Neither it nor `main.run`, `_build_current_pipeline`, `run_audit`, or
`build_event_intelligence_without_ai` is a ready shared worker. The no-AI path still
builds personal requests/context; the audit path still performs collection and writes.

Existing useful seams: collectors accept start/end and injected HTTP clients; weather
accepts explicit location; dedupe/price normalization accept values; pipeline separates
collection, intelligence and final curation; AI services accept explicit clients,
models/prompts/pricing; rendering is separate from Telegram delivery. Reuse these
implementations where their contracts fit, not a speculative new service framework.

An eventual independent worker must own explicit region/window/as-of configuration,
provider resources and permitted output, without calling the personal CLI. First
separate legacy settings imports and personal policy payloads under approved E1 scope.
Then evaluate a factual collection/analysis contract preserving provenance, unknowns,
failure status and broad recall. Only after that should E1 decide persistence,
scheduling, caching, retries/idempotency and later personalization boundaries.
Keep API lifespan free of any worker scheduler. No worker entrypoint is added here.

## 8. Current API/database/auth coexistence

`api/app.py::create_app()` creates routes/error/logging/CORS and application-owned
DatabaseResources. Lifespan disposes resources; it does not start research/migrations.
`api/dependencies.py::get_engine` lazily constructs resources, `database_healthy`
explicitly uses them for /health, and get_session resolves auth before DB resources.
`db/session.py` and models do not auto-create schema. Alembic alone creates schema.
`auth/config.py`, `api/config.py`, and `db/config.py` use process-level backend config,
not personal Settings. Token verification/JWKS/Auth calls occur when auth is requested,
not during import/lifespan. No API route imports main or research services.

Existing `tests/test_api_shell.py::test_api_import_and_lifespan_are_independent_of_private_runtime`
is sufficient current startup coverage: a fresh subprocess in an empty directory
blocks legacy config/main/services/collectors, OpenAI, Psycopg and Alembic imports;
blocks socket/DNS/subprocess activity, private-file opens and filesystem writes;
imports database models/session/health, starts/stops ASGI, and asserts no initial
engine. Unconfigured health returns 503, anonymous me 401, root 404 under guards.
It configures dummy Supabase values without fetching keys. Duplicating it adds no
new coexistence evidence. CLI help is separately verified without API/DB/Supabase
configuration. No runtime defect requiring code modification was found.

## 9. Known E1 risks and recommended investigation order

1. Freeze current personal behavior with existing fixtures/tests; do not run the live
   personal packet as a regression test. Preserve its CLI/workflow/policy unchanged.
2. Establish intended region/window and source coverage. Existing feeds are Sonoma-
   specific; current-time truncation and source-dependent IDs need explicit treatment.
3. Map and separate settings/telemetry import dependencies before claiming a pure
   reusable package. Add focused import guards for the chosen future worker surface.
4. Define factual versus personal semantic fields across request/card schemas and all
   three prompts. Remove neither personal behavior nor policy blindly; create the
   future shared path only under E1 authorization. Empty personal strings are not
   evidence of a depersonalized pipeline.
5. Reassess active hike compression and diagnostic-only event scores. Preserve source
   provenance, degraded statuses, uncertainty and partial-batch success; measure recall.
6. Design permitted artifacts and error/log handling. Audit output embeds private text;
   personal repository validation and Telegram errors are not public error envelopes.
7. Only then decide shared persistence/job identity, concurrency, cache/versioning,
   failure recovery and eventual personalized consumers. Current files have no
   multi-user partitioning, locks, durable shared run state or idempotent delivery.
8. Verify a separate worker with synthetic/public fixtures and controlled provider
   evidence. Keep API lifecycle, personal scheduler and Telegram delivery independent.

These are sequencing recommendations for the E1 lead, not a redefinition of E1 scope.

## 10. Verification and evidence limits

WP8 uses source tracing plus the established Python/web regression gates and API
isolation test. A clean-environment CLI help smoke provides the inverse compatibility
check; no production CLI run, audit, live collector, OpenAI or Telegram call is used.
Private file contents, live research quality, provider freshness and full billing
accuracy are outside this evidence. Deployed staging is not redeployed or reverified.

Accepted WP7 Actions run 37156432123 already proved 355 Python passes, one expected
hosted-Supabase skip, all five live PostgreSQL tests and 39 web passes. WP8 local
Docker access remains unavailable (`sudo -n` requires an owner password); local skips
are not new database evidence.
WP8 actual local results: `uv sync --frozen`, Ruff format/lint, mypy,
`git diff --check`, and CLI help passed. Pytest: 350 passed, six integration skips,
one existing Starlette/httpx deprecation warning. Web npm ci/lint/typecheck/tests/build
passed (39 tests). The clean-environment guarded CLI-help subprocess passed with
product imports, network, private-state reads and writes prohibited. No code/test
changes were needed; existing API guard was exercised in the full suite.

The WP7 push trigger names WP7 only. WP8 does not change it, dispatch production,
or open a PR without authorization. No fresh GitHub CI claim follows from a WP8 push.

## 11. Explicitly not implemented or verified

No shared regional universe, worker orchestration, depersonalized AI #1/#2, new
research persistence, per-user packets, profile/intent schema, schedules, billing,
entitlements, email, analytics or ChatGPT integration. No production/private policy
migration, concurrency hardening, catalog redesign or prompt changes. Multi-user
research suitability, recall, cost and isolation still require future E1 evidence.

Conclusion: the current personal engine and E0 API coexist through separate execution
boundaries. There is candidate reusable code, but the personal pipeline itself is
not yet a shared core. No WP8 architectural blocker requires altering production.
