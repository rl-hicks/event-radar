# E1 WP7 — Standalone shared regional worker

Implementation baseline: `22379b22fab436c975e7fcde0bb266a5c696a72c`.
Governance-only commit: `1220b6f`. Active authority: E1 Execution Roadmap v1.1.

## Execution

The independent module entrypoint is:

```sh
uv run python -m event_radar.shared_worker --synthetic \
  --region sonoma-county-ca --weekend 2026-10-09 \
  --as-of 2026-10-08T12:00:00-07:00 --policy-version synthetic-wp7
```

Set `TEST_DATABASE_URL` to the repository's dedicated disposable PostgreSQL
service, start that service, and apply Alembic migrations there first.
The CLI does not apply migrations. Synthetic mode rejects hosted databases, libpq overrides,
and policy names outside the synthetic namespace. It does not load dotenv,
legacy Settings, Telegram, personal state, FastAPI, or invoke OpenAI adapters in synthetic mode.

The reusable Python entrypoint is `run_regional_worker(scope, dependencies,
budget=..., refresh=False)` in `event_radar.shared.worker`.
Inject the existing WP3 source registry, WP4 semantic provider, WP5 planner,
researcher and independent verifier, and a PostgreSQL engine. The registry remains
source-agnostic; WP7 adds no production source adapters. The existing explicit
WP4/WP5 OpenAI adapters can now be composed through guarded real mode, documented
below. Executing that mode still requires separate owner authorization.

ResearchScope retains Sonoma County / America/Los_Angeles and Friday 00:00
through Monday 00:00 exclusive. The caller supplies Friday, as_of, and policy.
as_of is an explicit evidence cutoff, not a component of logical identity.

The worker calls existing collection/normalization/dedup, initial semantics,
adaptive discovery/independent verification/dedup, and semantics for newly
admitted discoveries or evidence merges that invalidated earlier descriptors, then persists the validated universe transactionally.
Coverage, factual exclusions, alternate provenance, stage token/cost/tool/latency
diagnostics and the discovery summary remain durable. Collection coverage never
asserts regional completeness. Zero results after successful attempts is valid;
no enabled sources, failed sources, or semantic/discovery fallback degrade status.

## Claim, retry and recovery

A dedicated PostgreSQL session takes a nonblocking advisory lock derived from
the established region/Friday/policy key **before** WP6 identity creation.
The lock spans research while run creation and completion use short transactions.
A same-key competitor returns `busy` without source/provider work or extra rows.
Different keys are independent. All worker callers must use this entrypoint;
WP6 low-level write functions are transaction primitives, not worker claims.

Use a direct or session-pooled PostgreSQL connection. Transaction-pooling
proxies are unsupported because session locks must stay on one backend.
The dedicated connection is invalidated/closed on exit, including cancellation,
so locks cannot leak into the pool. PostgreSQL releases locks on process death.
The next claimant marks abandoned running attempts failed before retry/replay.
No lease, clock-based takeover, schema redesign, or new migration is needed.

Successful same-key calls replay the stored snapshot with **no** research.
Changing wall-clock time/as_of does not change that behavior. `refresh=True`
(`--refresh` in the CLI) explicitly requests another attempt. Failed/partial
runs are retryable. Existing WP6 logical-key and content-hash uniqueness remain
in force. Failed/partial refreshes do not replace a successful current snapshot;
partial snapshots and failed attempts remain inspectable in WP6 tables.
Unexpected errors store only bounded codes, never raw exception strings.
Cancellation records failure when the database remains available; process/DB
loss leaves a running attempt for next-claim recovery.

Readers call WP6 `read_current_regional_universe` without collection or providers.
The returned quality is explicit; a first partial result is never labeled success.

## Budget and operational boundaries

The caller supplies WP5's bounded discovery budget, semantic batch size, and
a whole-research timeout. WP4 retains its bounded correction/fallback behavior;
WP5 retains model/search/wave/cost accounting and stop rules.
Cost estimates are model-token estimates, not all-inclusive invoices.
Synthetic fixture telemetry explicitly costs zero. The smoke configuration
values are test inputs, **not approved live spending limits**.

The separate Product Shared Research workflow is manual-only and synthetic-only,
with contents:read, same-key concurrency protection, quoted environment inputs,
a disposable database, no secrets and no Telegram/private dependencies.
There is no cron, deployment, hosted migration, or live-provider invocation.
Product Foundation CI remains separate and runs the PostgreSQL worker proofs.

Actual bounded public-provider/staging execution, worker-specific credential
provisioning, and weekly activation remain **pending separate owner authorization
and E1 execution-lead disposition** under roadmap WP7. A proposed eventual
Thursday run would resolve and pass an explicit Friday key in Pacific time;
no recurring schedule is configured here. Synthetic evidence does not satisfy
the roadmap's real-provider/active-operation gates. WP8 owns full two-profile
acceptance; WP7 proves repeated consumers can read one snapshot without research.

## Real public-only staging run — pending owner authorization

**Do not run this command until the owner approves a specific public-only run
envelope.** This capability does not satisfy WP7's real-provider acceptance gate,
does not authorize spending, and does not close governing WP7/E1 requirements.

Supply these secrets using a secure runtime environment, never command arguments
or checked-in files:

- `EVENT_RADAR_RESEARCH_DATABASE_URL`: explicit `postgresql+psycopg` URL with
  username, password, host, port and database. Remote targets require
  `sslmode=verify-full`. Only that URL query option is accepted.
- `EVENT_RADAR_RESEARCH_OPENAI_API_KEY`: dedicated worker API key.

No `.env` is loaded. Ambient `DATABASE_URL` and `OPENAI_API_KEY` are not
substitutes. Remove `PG*` libpq variables to prevent target redirection.
Use a direct PostgreSQL connection or session-mode pool; transaction pooling is
unsupported by WP7's advisory lock. The declared connection mode is an operator
assertion, not automatic proxy detection; known transaction-pool port 6543 is
rejected. Confirm the actual endpoint with the owner.

The target must already have Alembic `0002_regional_universes` applied (and its
`0001_app_users` predecessor). The command never migrates or creates schema.
Any hosted migration remains a separate approved operation.

Command template, **only after authorization**, from the repository's uv environment:

```sh
uv run python -m event_radar.shared_worker \
  --real --acknowledge-live-run --database-session-mode direct \
  --region sonoma-county-ca --weekend "$FRIDAY" --as-of "$AS_OF" \
  --policy-version "$RESEARCH_POLICY_VERSION" \
  --semantic-model "$SEMANTIC_MODEL" --discovery-model "$DISCOVERY_MODEL" \
  --timeout-seconds "$RESEARCH_TIMEOUT_SECONDS" \
  --semantic-batch-size "$SEMANTIC_BATCH_SIZE" \
  --max-waves "$DISCOVERY_MAX_WAVES" \
  --max-model-calls "$DISCOVERY_MAX_MODEL_CALLS" \
  --max-web-search-calls "$DISCOVERY_MAX_WEB_SEARCH_CALLS" \
  --max-model-cost-usd "$DISCOVERY_MAX_MODEL_COST_USD" \
  --semantic-pricing "$SEMANTIC_INPUT_RATE" "$SEMANTIC_CACHED_RATE" "$SEMANTIC_OUTPUT_RATE" \
  --discovery-pricing "$DISCOVERY_INPUT_RATE" "$DISCOVERY_CACHED_RATE" "$DISCOVERY_OUTPUT_RATE"
```

Every numeric field above must be explicitly supplied; there are no live model
or budget defaults. Pricing is USD per million input/cached-input/output tokens
for the selected models, provided explicitly rather than obtained from legacy
Settings or assumed current. The rates must be reviewed for the approved models.
The live acknowledgement is only a runtime guard, never evidence of owner approval.
Real mode rejects synthetic policy names. Friday and aware as_of validation use
the existing Sonoma/Pacific ResearchScope. A completed key replays unless the
owner-authorized command explicitly adds `--refresh`.

The runtime composes:

- Sonoma County Tourism public events;
- Happening in Sonoma County public events;
- the repository's curated Sonoma hike catalog;
- WP4 `OpenAIRegionalSemanticProvider`;
- WP5 `OpenAIAdaptiveDiscoveryProvider` as planner/researcher/independent verifier;
- the existing WP7 worker and WP6 PostgreSQL services.

Models come solely from the two CLI model flags. The runtime fixes OpenAI's
public API endpoint, disables SDK retries, and owns/closes the client and engine.
Its model transport ignores ambient proxy configuration. Public source adapters
retain their existing HTTP behavior. Prompt files are the four existing
`prompts/regional_*.md` assets; the catalog is `data/hikes.json`. These resolve
relative to the installed repository source, independent of shell cwd. No new
sources or source promotion are introduced.

WP5's estimated model-cost limit is a **discovery** limit checked between responses.
An in-flight response can exceed it. It is not a hard whole-run billing cap.
Semantic model usage is separately measured; web-search/tool fees and pricing
premiums are not included in model-token estimates. The owner must approve an
envelope covering both semantic passes, discovery, and tool charges, with explicit
provider-side spending controls as appropriate. Configuration values and a runtime
acknowledgement do not supply that authorization.

The Product Shared Research workflow remains synthetic-only and manual-only;
real execution is an explicit local/runtime CLI operation. No recurring schedule,
deployment, hosted migration, private-state access, personal User Context,
Telegram, legacy pipeline, or AI #3 is introduced or permitted by this capability.

## First live-proof failure and corrective observability

The one authorized attempt `ba52478e-1b92-4f6a-a0d8-98c0eba82761` failed after
collection recorded 109 candidates / 107 deduplicated opportunities. Its original
row contains no semantic telemetry and no snapshot. **The original root cause
remains unproven.** The corrective work does not refresh that key, overwrite its
evidence, or make further external provider calls.

Operational diagnostics now carry an optional bounded `failure_category`,
`provider_calls` (semantic service invocations, not a claim of billable calls),
and `attempts_complete`. Existing stored JSON remains readable using defaults;
no database migration is needed. Categories distinguish provider transport/status,
SDK parse/finish-reason, response schema/behavior, local validation/invariant,
configuration, cancellation and timeout failures. No exception message, arbitrary
class name, API body, request payload or credentials are persisted.

The semantic service checkpoints known batch usage and call accounting before
propagating unexpected errors. The worker persists the failing stage before
finalizing a failed attempt. Known numeric usage is a subtotal when the failed
call's usage is unavailable; `usage_complete=false` and
`attempts_complete=false` prevent treating unknown work as zero. Invalid numeric
telemetry cannot break failure reporting. Local errors use
`invalid_response` plus a local category rather than masquerading as provider
unavailability. Expected provider failures retain existing partial/fallback
semantics; neither partial nor failed retries replace the last-good snapshot.

The installed OpenAI SDK 2.53.0 inspection identified public
`APIResponseValidationError`, Pydantic/JSON parse errors, and Pydantic schema
construction errors outside the original boundary. The adapter now handles these
with bounded codes. Public `LengthFinishReasonError` and
`ContentFilterFinishReasonError` also receive defensive handling; those exceptions
are associated with chat-completion parsing, not evidence that the installed
Responses path or the first live run raised them. Incomplete/unsupported Responses
results are explicitly classified. Broad TypeError/RuntimeError catches are not
used to disguise programming defects as SDK availability failures.

Offline tests call the supported `AsyncOpenAI.responses.parse` API through
`httpx.MockTransport`, checking actual schema construction and valid/malformed
responses with external sockets blocked. No private SDK API is invoked. The
current semantic schema passes that offline contract test, which does not prove
remote model compatibility or explain the historical failure. On parsing errors
where the SDK does not expose response usage, cost remains explicitly unknown.
Only numeric usage exposed by known exception types is retained.

### Next authorized proof: recommend semantic batch size 10

Batch size 25 is not established as the cause. The request sends complete
opportunities, occurrence facts and evidence; the output contains an entry per
opportunity and a variable number of descriptors. Smaller batches reduce each
request/response's size and the number of candidates affected by a parse failure.

A validated synthetic event/hike request-size comparison (not the lost live input,
and not token counts) measured 8,267 bytes at 5 items, 15,330 at 10 and 38,420 at 25.
Recommend **10** for the next separately authorized development proof. For 107
candidates this means 11 initial batches rather than 5 at size 25, with up to one
reference-correction call per batch under existing WP4 rules. This increases
request overhead and must be included in the owner-approved timeout/spend envelope.
The global/default batch size remains 25; no product policy is changed.

The original disposable evidence database must not be used by the destructive
pytest migration fixture. Corrective local tests ran in a separate PostgreSQL
container network namespace, preserving the normal localhost/55432 safety guard.
The original failed-row JSON SHA-256 before corrective tests was
`34a23f40730f7fcb8cc9f4f02a9cdc78ea6e846337e65c5101a58875f2f4fe74`;
verify it again after testing. This is preservation evidence, not a new live-run
acceptance or WP7 closure.


## Semantic-input preflight correction (second proof)

Run `12b19362-4705-46b3-a98b-39acb5562e0c` recorded four completed semantic
calls / 40 results before `invalid_response / local_validation`. No fifth
call or discovery was recorded. Its item-level inventory was not saved, so an
exact historical payload comparison is unavailable.

The owner-authorized **deterministic collection-only** diagnostic reproduced
109 candidates / 107 retained on 2026-10-06 at 00:14 Pacific. The first four
10-item requests validated; request five failed `outside_region` for:

- Opportunity: `event-4e1959185cd21047e1dc` (zero-based inventory index 46).
- Source: `happening-sonoma-county`.
- Source-reported city/subdivision: `Cloverdale` / `SC`.
- Adapter-assigned county: `Sonoma County`; required subdivision: `CA`.

The reproducible defect originates at **source admission**, not deduplication
or semantic transformation. The adapter accepted the source's conflicting state
while assigning the requested county. An individual RegionalOpportunity does
not encode the research scope; RegionalAnalysisRequest correctly rejected it.
The semantic service previously constructed requests only immediately before
each call, allowing four paid batches before discovering this local defect.
This explains the reproduced failure pattern; it does not prove byte-for-byte
identity with the unsaved historical inventory or establish the original first
proof's root cause.

The event adapter now checks the source subdivision and weekend before admitting
a candidate and validates each admitted candidate against the scope. Established
California aliases (CA/California, whitespace/case) normalize to CA. A conflicting
subdivision is retained as an explicit `outside_region` factual exclusion with
source/record identity; it is not rewritten to California based on a city name.
This exclusion reflects the source-reported boundary conflict, **not** a claim
that the actual event is proven to be in South Carolina. Confirming or correcting
that source fact requires separate evidence. No regional invariant was relaxed.

`preflight_semantic_inputs(scope, opportunities, batch_size=...)` is a pure
entrypoint in `event_radar.shared.semantic_input`. Before the first provider
call of either enrichment pass, it revalidates every original candidate from its
serialized fields, validates the complete inventory (including duplicates across
batch boundaries), then prepares and validates every intended request. The service
reuses those prepared requests. No malformed input is silently removed by
preflight; failure aborts enrichment with zero provider calls.

Safe persisted `input_failure` diagnostics contain phase, one-based batch number,
up to two public opportunity identifiers, up to eight source identifiers, and
a finite rule code: duplicate opportunity identity, duplicate occurrence identity,
outside region, outside window, observation after as_of, or other contract
violation. They never copy arbitrary Pydantic messages, input/context dictionaries,
payloads or API responses. Preflight failures explicitly record zero attempts,
tokens and cost with complete zero-call accounting. Existing JSON remains readable;
no database migration is required.

Corrected collection-only verification at 00:21 Pacific retained:
12 Tourism + 71 Happening + 25 hikes = 108 admitted before deduplication,
106 after two duplicates, plus one explicit outside-region exclusion.
All 11 prepared batches (ten of 10, one of 6) passed preflight.
Neither OpenAI nor the shared-worker module was imported by that diagnostic.

Regression fixtures reproduce the SC/Cloverdale conflict synthetically, show
batch-five rejection before call one, exercise a valid 107-item inventory through
11 fake-provider batches, reject cross-batch duplicates and malformed nested
inputs, and prove safe persisted preflight failure/last-good protection against
a separate disposable PostgreSQL instance. No live model or web-search call was
made, and no new research attempt/snapshot was written to the preserved database.

Preserved full-row JSON SHA-256 fingerprints:
- `ba52478e-1b92-4f6a-a0d8-98c0eba82761`:
  `34a23f40730f7fcb8cc9f4f02a9cdc78ea6e846337e65c5101a58875f2f4fe74`
- `12b19362-4705-46b3-a98b-39acb5562e0c`:
  `d38ae1ffe9f89a8c18a2b8bd945628e9c80d235ba7b1073ad7270828b8b9a43b`

The preserved evidence database must remain outside destructive test fixtures.
This correction does not authorize another live proof or close WP7.
