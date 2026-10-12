# E1 WP7 durable development evidence and offline discovery

This bounded implementation starts at `ad2b17d3e954df7ab8c3ce2bcbb5a5e453ad25ee`
on `e1/shared-regional-intelligence`. PR #2 remains draft. WP7 and E1 remain open.

## Retained local evidence

`docker-compose.evidence.yml` owns Compose project `event-radar-evidence`,
service `evidence`, container `event-radar-development-evidence`, database/user
`event_radar_evidence`, and named volume `event-radar-development-evidence-data`.
PostgreSQL 17 listens on host loopback **127.0.0.1:55433** only. This is separate
from disposable tests on 55432 and from hosted Supabase. No tmpfs is used.
The volume survives service stop/start and container recreation. It is local
retention, not an off-machine backup; keep exported evidence separately when needed.

From the worktree, with Docker access, initialize a local-only password once.
The ignored `.env.evidence` file must never be committed or printed in logs:

```bash
# Once only; refuses to overwrite an existing file.
python3 - <<'PY'
from pathlib import Path
import secrets
path = Path(".env.evidence")
with path.open("x") as f:
    path.chmod(0o600)
    f.write("EVIDENCE_DB_PASSWORD=" + secrets.token_hex(32) + "\n")
PY
set -a
. ./.env.evidence
set +a
export EVIDENCE_DATABASE_URL="$(uv run python - <<'PY'
import os
from sqlalchemy import URL
print(URL.create(
    "postgresql+psycopg", username="event_radar_evidence",
    password=os.environ["EVIDENCE_DB_PASSWORD"], host="127.0.0.1",
    port=55433, database="event_radar_evidence",
).render_as_string(hide_password=False))
PY
)"
docker compose --env-file .env.evidence -f docker-compose.evidence.yml up -d --wait evidence
DATABASE_URL="$EVIDENCE_DATABASE_URL" uv run alembic upgrade head
DATABASE_URL="$EVIDENCE_DATABASE_URL" uv run alembic current
```

Use the existing E1 migration head `0002_regional_universes`. Do not apply
downgrades to retained evidence. Remove any inherited libpq `PG*` overrides
before operating; the inspection CLI rejects them and rejects all alternate
hosts, ports, database names, users and URL query options. Do not inherit a
hosted `DATABASE_URL`; pass the explicit local URL above to Alembic.

Routine lifecycle commands (no volume removal):

```bash
docker compose --env-file .env.evidence -f docker-compose.evidence.yml stop evidence
docker compose --env-file .env.evidence -f docker-compose.evidence.yml start --wait evidence
docker compose --env-file .env.evidence -f docker-compose.evidence.yml restart evidence
docker compose --env-file .env.evidence -f docker-compose.evidence.yml exec -T evidence pg_isready -U event_radar_evidence -d event_radar_evidence
```

## Inspect and export

List IDs without reading private account tables:

```bash
docker compose --env-file .env.evidence -f docker-compose.evidence.yml exec -T evidence psql -U event_radar_evidence -d event_radar_evidence -c 'SELECT id, as_of, quality_status, content_hash FROM regional_universe_snapshots ORDER BY as_of;'
uv run python -m event_radar.development_evidence export --snapshot-id SNAPSHOT_UUID
uv run python -m event_radar.development_evidence export-run --run-id RUN_UUID
uv run python -m event_radar.development_evidence discover-offline --snapshot-id SNAPSHOT_UUID
```

All three commands use database-enforced read-only transactions and verify the live
database/user identity. The discovery command accepts no live mode, provider/model selector,
API key, or user context. A process-lifetime audit guard rejects OpenAI/live
adapter imports, Python socket connection/DNS operations and subprocess launches.
Its only I/O connection is the explicitly guarded local PostgreSQL connection
through libpq. Fixed in-process fakes exercise existing WP5 planning, research,
independent fixture verification, deduplication, budgeting and stop conditions.
Synthetic results are diagnostic output only and are never inserted into the base.

Exports are UTF-8 JSON under ignored `output/development-evidence/`, with unique,
non-overwriting filenames. The envelope format is `event-radar-public-evidence-v1`.
Its `sha256` is SHA-256 of `payload` serialized using Python JSON with
`ensure_ascii=False, sort_keys=True, separators=(",", ":")`. Snapshot content has
a separate WP6 hash checked before readback. The export retains the validated
universe schema, identity, scope/as_of, provenance, semantics, exclusions,
diagnostics, snapshot quality, discovery summary/operations and related identity
runs (including failures and runs for other snapshots). Only regional tables
and explicit safe run columns/validated diagnostic models are read. Credentials,
private account data and raw provider exception bodies are not exported.

Missing IDs produce `availability: unavailable` with `record: null`; they never
produce a purported historical record. To verify retained evidence, export the
same ID before stop and after start and compare envelope hashes (new related
research runs legitimately change an export). Unknown token/tool/cost values stay
null. Known totals remain subtotals, completeness flags remain intact, and model
estimates exclude tool fees.

The diagnostic includes base ID/hash/scope, initial/final coverage, each returned
plan/research result/verification decision, new unique opportunities, exclusions,
bounded operation telemetry, status and stop reason. Fatal interruption marks the
returned new-opportunity list incomplete while retaining known wave counts. Failed calls appear in
operation evidence even when no result was returned. Remaining gaps are the last
planner assessment and are explicitly incomplete unless a terminal plan observed
the final inventory. No claims of regional completeness follow from the fake plan.
WP6 does not retain historical source-class assessments; reconstruction marks all
classes conservatively unsearched and reports the limitation. It does not infer
history from today's registry. Existing snapshot provenance and semantics remain
immutable even when WP5 proposes a duplicate merge in memory.

## Regression isolation

Routine pytest fixtures accept only database/user `event_radar_test` at
127.0.0.1:55432 with no URL query overrides; they also verify live database/user
identity before destructive migration. They reject the evidence URL. Do not
change these guards or point `TEST_DATABASE_URL` at retained evidence.

```bash
uv run pytest tests/test_development_evidence.py tests/test_regional_persistence_integration.py
# Requires Linux root/Docker access and installed locked .venv dependencies:
sudo python3 scripts/test_evidence_restart.py
```

The pytest database tests require a separately isolated disposable test instance.
The restart script creates unique `event-radar-wp7-restart-test-*` containers and
volumes with `--network none`, no published ports, and synthetic credentials.
It applies real migrations, inserts only the public synthetic fixture, exports,
stops/starts, validates identical readback, runs the fake CLI, and checks the base
again. Cleanup removes only its own uniquely generated disposable resources.
It never operates on the retained evidence or historical stopped containers.
Product Foundation CI runs this restart proof in addition to its existing suite.

## Historical and future execution boundaries

The historical 106-opportunity run was reportedly stored in temporary PostgreSQL.
Its lost records remain unavailable, not reconstructed. Historical failure cause
remains inconclusive; see `e1-wp5-discovery-correction.md`. New retained storage
and synthetic regression evidence do not recover or independently verify that run.

The provider-neutral `shared.discovery_only.diagnose_snapshot` API accepts explicit
planner/researcher/verifier dependencies and a budget, reusing WP5 contracts.
There is no WP3 or initial WP4 invocation, no shared-worker run record, no snapshot
write, no personal context, Telegram or E2 path. Optional incremental WP4 enrichment
is deliberately omitted. A future live composition needs separate owner approval
of the base snapshot/region/weekend, current research as_of/freshness policy,
permitted providers/tools, total spend, call/search/time/retry bounds, credentials,
and retention of diagnostic output. The offline command must remain fake-only.
A separate live entrypoint would inject existing adapters, use an explicit updated
observation scope without silently changing the base, and preserve diagnostics;
it would not certify completion of a weekly worker run.

Local verification: 663 Python passes, one expected opt-in hosted Supabase skip;
17 focused passes; real stop/start/readback and fake CLI proof passed; 39 web tests,
ESLint, TypeScript, production build, Ruff, strict mypy (87 files), security scans,
CLI help and Alembic metadata passed. The handoff records the final SHA and actual
CI result. No real provider call, public collection, hosted database contact,
deployment, schedule activation or historical container modification occurred.

Retained service setup was also exercised locally: the dedicated Compose database
received migrations through `0002_regional_universes`, contained zero snapshots,
and was stopped with its named volume retained. Its generated local credential is
in ignored `.env.evidence` (mode 0600); no historical or synthetic record was
inserted into this retained database.


## Run-ID export correction

A failed first attempt needs no snapshot to export:
`uv run python -m event_radar.development_evidence export-run --run-id RUN_UUID`.
It uses the same dedicated target, read-only transaction, live identity check,
ignored output directory, unique filenames and `event-radar-public-evidence-v1`
SHA-256 envelope. Its payload contains `availability`, `universe_id`, validated
`identity` (region_id, Friday, research_policy_version), `record` and `snapshot`.
The record preserves run ID, requested as_of, started/finished timestamps, status,
bounded failure code, validated stage diagnostics and discovery summary/operations.
Unknown usage remains null and completeness flags remain unchanged.

`snapshot` is null when absent; otherwise it identifies the integrity-checked
linked snapshot with ID, quality status, content hash and universe schema version.
This run export does not fabricate or embed a universe; use snapshot export for
the full universe when available. Missing runs return `availability: unavailable`,
`requested_run_id` and `record: null`. Invalid diagnostic envelopes, stage records,
operations or failure codes fail without writing an export; CLI errors omit raw
validation inputs and exception bodies. No account tables or arbitrary row blobs
are exported. The existing snapshot exporter reuses the same safe run serializer.

## Separate execution-lead verification status

Per the E1 execution lead's supplied verification, current model compatibility and
published pricing have been verified. This is recorded lead-provided evidence,
not a new provider check by this correction. Actual project-key access and a
strict whole-run monetary cap have **not** been established. This correction
does not authorize live execution, change research behavior, or close WP7.


Correction verification: **27 focused tests passed**, **673 full Python tests
passed**, one expected hosted Supabase skip, and **39 web tests passed**. The
isolated Docker lifecycle proof also exercised actual run-export CLI invocations
with and without snapshots and verified hashes. Tests compared all regional rows
before/after read-only export and checked safe rejection of corrupt diagnostics.
Ruff, mypy, source/build security, web lint/types/build, CLI help and Alembic
metadata gates passed. Retained evidence was not accessed or modified during
this correction; all database testing used disposable network-isolated instances.
