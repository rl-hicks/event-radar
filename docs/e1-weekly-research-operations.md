# E1 weekly shared research: operating proposal (inactive)

Implementation base: `2fda42d87f509610fd70bb66d591253de809b3ba`, branch
`e1/shared-regional-intelligence`, draft PR #2. This document proposes activation;
it does not authorize spending, hosted changes, deployment, merge, or E2.
WP9's live weekly-operation gate remains pending. Configured infrastructure is
not evidence of successful recurring operation.

## Schedule and execution

`.github/workflows/product-weekly-research.yml` contains a manual planning job.
The research job has a literal `if: ${{ false }}`; the schedule is commented out.
Neither repository variables nor dispatch can enable paid execution in this state.

Proposed cadence: Thursday 12:15 America/Los_Angeles for the upcoming Friday–Sunday,
using `cron: '15 12 * * 4'` and `timezone: America/Los_Angeles`.
GitHub now supports IANA timezones in schedule entries
([workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax),
[March 2026 announcement](https://github.blog/changelog/2026-03-19-github-actions-late-march-2026-updates/)).
This is 20:15 UTC in PST and 19:15 UTC in PDT. Noon avoids ambiguous/missing DST
hours; e.g. March 5/12, 2026 change from 20:15 to 19:15 UTC; November 5 is 20:15.
Scheduling operates on the default branch and may be delayed or dropped. It is
not a guaranteed delivery-time service. The operator must check by Friday morning
that the expected logical weekend exists; no automatic catch-up is authorized.

The plan job reads the workflow run's immutable `created_at` from GitHub. Reruns
retain that anchor, rather than silently selecting another weekend. Execution
rejects anchors older than 24 hours, future anchors, days other than Pacific
Thursday/Friday, and manually supplied Fridays inconsistent with the anchor.
The fresh worker `as_of` is Pacific-aware. The identity is region + Friday +
policy, not the workflow attempt ID or `as_of`.

The scheduled adapter invokes existing `execute_real` with `attempt_once=True`,
never legacy `event_radar.main`. Sonoma Tourism, Happening in Sonoma County,
curated hikes, WP4 semantics, WP5 planning/research/verification, and WP6/WP7
persistence remain the production composition. No user count, user identity,
preferences, Telegram, packet generation, or AI #3 enters that path.

GitHub concurrency groups use the logical key with `cancel-in-progress: false`.
The decisive protection is PostgreSQL: while holding the existing session
advisory lock, the worker checks for **any prior attempt**, before abandoned-run
recovery or new provider work. Success replays; partial, failed, or still-running
attempts block spending. A concurrent caller returns busy. No automatic retry,
refresh, or policy-version bump is permitted. Existing manually authorized worker
recovery behavior remains unchanged outside this opt-in scheduled path.

## Proposed retained hosted target (approval required)

The local evidence service at 127.0.0.1:55433 cannot serve a GitHub-hosted runner.
Prefer the intended Supabase PostgreSQL project only after the owner identifies
the correct environment and approves E1 co-location, privileges, and migrations.
Do not infer its migration or deployment state from repository configuration.

For an IPv4 GitHub runner, propose Supavisor **session mode on port 5432**, with
the exact host and role-specific username from the project's Connect configuration.
Direct access is acceptable only after connectivity/IPv6 has been verified.
Transaction pooling (6543) cannot preserve the worker's session advisory lock
([Supabase connection documentation](https://supabase.com/docs/guides/database/connecting-to-postgres)).

Configure protected GitHub environment `shared-regional-research`:

- Secrets: `EVENT_RADAR_RESEARCH_DATABASE_URL`,
  `EVENT_RADAR_RESEARCH_OPENAI_API_KEY`,
  `EVENT_RADAR_RESEARCH_DATABASE_CA` (approved PEM root certificate).
- Variables: `EVENT_RADAR_RESEARCH_EXPECTED_HOST`,
  `EVENT_RADAR_RESEARCH_EXPECTED_DATABASE`,
  `EVENT_RADAR_RESEARCH_EXPECTED_USER`, and, only after operating approval,
  `EVENT_RADAR_SCHEDULE_APPROVED=true`.
- Restrict environment access to the approved default branch. Require a reviewer
  for initial controlled activation; separately decide whether to remove that
  per-run approval to permit unattended recurrence.

The DSN must explicitly name host, port, user/password, and database, and use
`postgresql+psycopg://…?sslmode=verify-full`. The workflow installs the approved CA
as `~/.postgresql/root.crt` with private permissions. No other URL options or
inherited `PG*` variables are allowed. A read-only preflight verifies actual
database/user and migration `0002_regional_universes`; a mismatch stops before
live adapter creation. Database errors are not printed. Hosted reachability,
certificate validation and privilege sufficiency still need authorized testing.

### Forward migration and role proposal — do not execute yet

Use a separate migration credential, never the research role. After approving
the exact hosted target, supply `DATABASE_URL` securely to Alembic without shell
tracing or printing it. Proposed commands from the reviewed checkout:

```bash
set +x
uv run alembic current
uv run alembic upgrade 0002_regional_universes
uv run alembic current
```

Only approve the upgrade after inspecting the current revision. From
`0001_app_users`, approve precisely the 0002 forward migration; an empty,
unknown, or divergent history needs separate reconciliation. No stamp, downgrade,
reset, hosted test fixture, or automatic workflow migration is allowed.

Proposed grants, to be reviewed against existing hosted grants/RLS and actual
database/schema names, not run by this assignment:

```sql
CREATE ROLE event_radar_research NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
  NOINHERIT NOBYPASSRLS;
GRANT CONNECT ON DATABASE postgres TO event_radar_research;
GRANT USAGE ON SCHEMA public TO event_radar_research;
GRANT SELECT ON public.alembic_version TO event_radar_research;
GRANT SELECT, INSERT, UPDATE ON public.regional_universes,
  public.regional_research_runs, public.regional_universe_snapshots
  TO event_radar_research;
```

Verify exact table names against 0002 before approval. An operator must provision
the LOGIN credential through a secure administrative channel and configure the
pooler's role/project username. Do not put a password literal in checked-in SQL.
No DELETE, schema ownership/DDL, account/auth-table access, or migration privilege
is needed. Verify inherited/PUBLIC privileges and Supabase Data API exposure;
approve revocation of unwanted PUBLIC/anon/authenticated E1-table grants if needed.
Do not modify E0 account grants. Prove the resulting role can perform the guarded
worker transaction and cannot read private tables before activating paid execution.

## Whole-worker envelope and costs

`config/shared-research-envelope.json` is a non-authorizing starting proposal:

| Scope | Proposed control |
| --- | --- |
| Models | GPT-6 Luna for WP4 and WP5, standard processing |
| Pricing reference | input $0.10, cached input $0.01, output $0.50 per million tokens |
| Semantic batching | 10 opportunities |
| Entire worker | 24 model calls, $0.25 accumulated estimated model-token threshold |
| WP5 subset | one wave, six model calls, six observable web-search calls, $0.10 model-token threshold |
| Time | 600-second worker deadline; 15-minute job deadline |
| Retries | SDK retries zero; no workflow/provider-attempt replay after persisted attempt |

The shared guard covers initial semantics, semantic correction attempts, planning,
research, verification, and optional enrichment of new discoveries. It refuses
further calls after unknown token usage, a provider exception, exhausted call
count, or reaching its post-response estimate threshold. Existing WP5 tool budgets
remain in force. A guard denial uses the existing bounded configuration failure
classification with zero attempted provider calls; it does not invent usage.

These are **not hard whole-run monetary caps**. A final response can overshoot a
threshold; timeout/cancellation can leave server-side work billed and usage
unknown. Web-search fees are outside model-token estimates. Six observable tool
calls are a control, not evidence of a complete invoice. Planning may properly
stop without searches, and no search quota is forced.

The historical October 16 proof cost $0.0229426 in known model tokens (11 semantic
calls and one planner call), with no research/verification. That is a useful
baseline, not a forecast for an adaptive research week. Propose approximately
$1 per attempted week, $4–$5 per calendar month, with owner review of each initial
run. Within that planning allowance reserve $0.20 for tool fees/uncertainty; this
is a budgeting allowance, not a verified tool tariff. Actual adaptive-run costs
remain unmeasured. Reverify model/project-key compatibility, current input/cache/
output pricing, processing tier and web-search fees at activation; adjust the
explicit approved envelope if needed. No silent model substitution is allowed.

For infrastructure, reuse of an already funded project may have no incremental
base charge within its quotas. Supabase Free currently has a 500 MB limit, can
pause after a week of inactivity, and lacks automatic backups; it is unsuitable
as an assumed unattended retention guarantee. Pro starts at $25/month including
the first project, with daily backups retained seven days
([pricing](https://supabase.com/pricing)). A new Pro project plus the proposed
research allowance is roughly $29–$30/month before overages/taxes. Standard public
repository Actions runners are free; private runner minutes and artifact storage
depend on account quotas
([Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)).
These are proposals, not provisioned services or approved indefinite charges.

## Evidence, notifications and recovery

PostgreSQL remains authoritative across runner termination. Attempt creation is
committed before research. Crash-released advisory locks do not authorize retry:
a retained running row blocks a new scheduled attempt. Last-good snapshots are
preserved by the existing publication contract.

The adapter exports allowlisted validated run-ID and linked snapshot-ID evidence,
using existing SHA-256 integrity envelopes, to ignored
`output/development-evidence/schedule-evidence-<uuid>.json`; a separate
`schedule-receipt-<uuid>.json` records identity, proposed envelope, invocation
start/end, bounded status, IDs, database/evidence status and accounting. Run
records retain actual start/end, source/stage diagnostics, planning decisions,
failure classifications and known/unknown costs. Missing records are explicitly
unavailable. No prompt, provider exception body, environment dump, credential,
account table, or user context is exported.

The workflow uploads only those explicit files, named by GitHub run/attempt, with
30-day artifact retention. Nested run and snapshot envelopes each retain their
own hash; verify each canonical payload with the existing `integrity_envelope` helper after downloading:
```bash
uv run python - <<'PY'
import json
from pathlib import Path
from event_radar.db.evidence import integrity_envelope

def verify(value):
    if isinstance(value, dict):
        if value.get("format") == "event-radar-public-evidence-v1":
            assert value == integrity_envelope(value["payload"]), "Integrity mismatch"
        for child in value.values():
            verify(child)
    elif isinstance(value, list):
        for child in value:
            verify(child)

paths = list(Path("output/development-evidence").glob("schedule-*.json"))
assert paths, "No exported evidence"
for path in paths:
    verify(json.loads(path.read_text()))
    print(path.name, "verified")
PY
```

SHA-256 proves content consistency, not authorship. Proposed database retention is
at least 90 days of run/snapshot history, without an automatic deletion job.
Approve backup ownership, recovery objectives and durable export retention
separately; ephemeral runner files and 30-day artifacts alone are not backups.

Only success/replayed results with complete observable accounting exit zero.
Partial, failed, busy, blocked, incomplete-usage, or export failures exit nonzero.
Tool fees and billing totals remain unknown unless established separately; zero
search fees are recorded only when complete telemetry proves zero tool calls.
Generic Actions failure annotations contain no exception bodies.

The operator must enable and test GitHub Actions failure email notifications for
the relevant maintainer account/repository, including failures initiated by the
schedule actor. Do not assume all repository watchers receive these notifications.
Validate delivery with a non-provider failure before activation. No new email,
Telegram, webhook, or paid alert service is implemented. A dropped schedule may
produce no failure notification: the Friday check remains an explicit operational
responsibility until an independently approved missed-run monitor is established.

Read-only recovery with the same approved database identity/TLS environment needs
no model key and never creates a run:

```bash
uv run python -m event_radar.shared_schedule export   --config config/shared-research-envelope.json --weekend YYYY-MM-DD
```

Inspect/export first after a failure. Do not rerun with a new policy just to bypass
idempotency. Additional provider work, abandoned-run recovery, refresh or changed
budgets requires explicit owner authorization and a separately reviewed manual
worker command. Preserve the original attempt and last-good snapshot. If a runner
is killed before export, use the read-only recovery command when connectivity is
restored; never reconstruct missing evidence.

## Activation checklist still requiring decisions

1. Approve the exact persistent project/environment, costs, operator, retention
   and backup/recovery arrangement. Verify staging deployment source separately.
2. Approve and perform target-specific forward migration and least-privilege/TLS
   setup; verify E0 security and E1 database contract without provider work.
3. Verify model/key access and published pricing/tool fees; approve the complete
   envelope, monthly spending expectation, failure notification route and
   missed-run responsibility.
4. Review/merge only with separate authority. In a reviewed activation commit,
   replace the literal false gate with approved default-branch plus approval
   variable checks, then enable the timezone-aware schedule. Retain the CLI
   acknowledgement, protected environment and atomic no-repeat protections.
5. Separately authorize a controlled first attempt/observation and recurrence.
   Inspect exported evidence and accounting. Establish actual weekly operation
   before claiming the E1 weekly acceptance outcome. No personalized packet is
   produced by completing this process.

See [E2 integration note](e2-first-user-vertical-slice-integration.md) for the
separate, unimplemented downstream product milestone.


## Offline verification for this implementation

Local full-suite result: **729 Python tests passed**, one expected opt-in hosted
Supabase skip; **39 web tests passed**. Ruff format/lint, mypy (89 source files),
tracked-source and built-web security scans, frontend lint/typecheck/build, CLI
help and Alembic metadata checks passed. The isolated Docker restart regression
passed fresh migrations, synthetic persistence, stop/start, validated readback,
run/snapshot export integrity and fake discovery without external network.
Product Foundation CI additionally requires the scheduled success/partial/failed/
abandoned replay cases and concurrency test to pass against real disposable
PostgreSQL; it retains all previous E0/E1, two-consumer and restart gates.

The 27 schedule-specific tests cover Pacific/DST identity, stale/manual triggers,
atomic replay and failure blocking, concurrent claims, last-good preservation,
whole-worker limits including incremental semantics, unknown accounting,
authorization, local-target rejection, migration mismatch, safe exports and
fresh-process import/network/private-state isolation. Destructive tests ran only
against a task-owned network-isolated disposable database. Neither retained
development evidence nor hosted databases were accessed. No provider or event
collection calls, recurring execution, deployment or E2 implementation occurred.

Changed implementation files:

- `.github/workflows/product-weekly-research.yml`
- `.github/workflows/product-foundation-ci.yml`
- `config/shared-research-envelope.json`
- `src/event_radar/shared_schedule.py`
- `src/event_radar/shared/spend_guard.py`
- `src/event_radar/shared/worker.py`
- `src/event_radar/shared_runtime.py`
- `src/event_radar/db/config.py`
- `tests/test_shared_schedule.py`
- `tests/test_shared_schedule_integration.py`
- `tests/test_shared_runtime.py`
- `docs/e1-weekly-research-operations.md`
- `docs/e2-first-user-vertical-slice-integration.md`

The implementation commit and exact-head CI run are reported in the handoff.
Historical recovery, governing artifacts and the preserved October 16 evidence
remain unchanged; draft PR #2 remains unmerged.
