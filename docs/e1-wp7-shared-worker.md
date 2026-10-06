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
The CLI does not apply migrations. It rejects hosted databases, libpq overrides,
and policy names outside the synthetic namespace. It does not load dotenv,
legacy Settings, Telegram, personal state, FastAPI, or OpenAI adapters.

The reusable Python entrypoint is `run_regional_worker(scope, dependencies,
budget=..., refresh=False)` in `event_radar.shared.worker`.
Inject the existing WP3 source registry, WP4 semantic provider, WP5 planner,
researcher and independent verifier, and a PostgreSQL engine. The registry remains
source-agnostic; WP7 adds no production source adapters. The existing explicit
WP4/WP5 OpenAI adapters can be composed by a separately authorized runtime;
this change intentionally supplies no live-provider CLI mode or credentials.

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
