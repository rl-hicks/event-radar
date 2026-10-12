# E2 AI #3 and canonical Weekend Packet implementation

Status: bounded offline package implemented for independent execution-lead review.
Neither E1, E2 nor V1 is accepted or closed. PM reconciliation remains pending.
Authority: owner's Personalized Curation & Canonical Weekend Packet assignment;
[controlled overlap decision](e2-controlled-overlap-decision.md).
Starting HEAD: `351808b8a67308f11a767993b8f3c66dc94a5368`.
Branch/worktree: `e2/first-user-vertical-slice`, `/home/robot/dev/event-radar-e2`.
Both local and remote E2 refs matched that clean baseline before changes.
Explicit unmerged E1 dependency: `26b454f41c3513de29f8e3a2bdada5f82185e421`,
`e1/shared-regional-intelligence`, draft PR #2. No E1 branch or governing artifact changed.

## Request, judgment, and factual boundary

`PersonalizedRequest` v1 contains the complete validated regional universe, its
snapshot UUID/hash, scope (region, weekend, research policy, as-of), research quality,
and validated private context revision UUID/hash/schema/content. The provider does
not receive the account UUID, credentials, database access, delivery bindings or tools.
Free text is data, not authority. No historical private context is read.

`CurationPolicy` pins policy/prompt/provider/model/configuration revisions, research
compatibility, maximum recommendation count, input bounds, timeout and output tokens.
Default bounds: 500 opportunities, 500,000 UTF-8 request bytes, 12 recommendations,
6,000 output tokens, one provider invocation within 30 seconds. User output maximum
can lower the recommendation bound. Configuration itself has hard upper limits.
The complete universe is included or the operation fails before any call. Nothing
is silently truncated or personally filtered before regional persistence. This is
deliberately a bounded first implementation, not retrieval infrastructure.

Research must match the explicitly configured policy, be no older than the policy's
96-hour default, not be future-dated, and concern an unexpired weekend. These are
explicit development applicability rules, not a promise of fresh ticket availability.
The internal operation accepts a clock override for deterministic testing.

`CurationResult` v1 returns success/partial and zero to 18 judgments. Each references
a real opportunity and its own evidence, optional semantic indices and supplied context
list items, expected experience value, recommendation strength, friction disposition
and tradeoff dimensions. The versioned prompt requires cost/travel/schedule/commitment/
solo judgment, exceptional high-friction options, no quota padding, and distinctions
between spectatorship, participation, co-presence, circulation and natural/structured
interaction. Crowds, alcohol and venue labels are not social-value evidence.

**Intentional v1 design decision:** AI #3 supplies bounded judgment codes and references,
not free-form prose. The application renders a rationale from those codes and the
referenced supplied preferences, while copying the entire selected opportunity from
the validated snapshot. This prevents arbitrary generated prices, venues, schedules,
access/availability claims, personal attributes, prompt text, or unexpected private fields
from entering the canonical response. Numeric ranking and invented travel estimates
are absent. Semantic descriptions remain research-backed, not generated again.
Judgment quality still requires later real-provider evaluation; enum validation cannot
prove an option is actually worthwhile.

Validation rejects unknown/duplicate opportunity IDs, foreign/duplicate evidence,
invalid semantic/context indices, duplicate tradeoffs, invalid enum/extra fields,
oversized outputs and inconsistent exceptional judgments. Regional validation
rechecks evidence/time/window/region integrity. Unknown/conflicting price, attendance,
access, missing end times and source unknowns survive packet construction; unverified
personal travel time is explicitly retained. Oversized source-derived text fails
validation rather than being silently shortened.

## Provider and diagnostics

`CurationProvider.curate` is replaceable. `DeterministicCurationProvider` uses synthetic
token overlap for offline differentiation; it is explicitly **not** a production ranking
algorithm. The OpenAI Responses adapter follows the installed SDK pattern, with
structured parsing, `store=False`, no tools, explicit output/timeout bounds and
`max_retries=0`, including for an injected client. It reads no environment or keys.
Construction is inert; execution requires explicit `authorized=True`, an OpenAI policy,
and an injected client or explicit key. No public API constructs/invokes it.

Provider errors become a small safe code vocabulary; raw errors, responses and prompts
are not stored/logged. SDK response status and unsolicited tool output are checked.
Shared pure token parsing/sanitization utilities are reused, with no E1 discovery call.
Known counts/cost estimates are retained; missing counts/cost remain null with incomplete
usage. Estimates are model-token-only and depend on explicitly supplied pricing, never
an embedded live price assumption. Fake calls report zero tokens/cost/network calls.
Latency is measured by the service. A timeout without a returned response leaves billing
usage unknown. No automatic retries or correction calls occur.

## Canonical schema and persistence

`WeekendPacket` v1 stores account, packet/execution/curation IDs, region/weekend,
snapshot/context UUIDs and hashes, research as-of/quality, full policy, prompt hash,
creation time, separate personalization and combined success/partial statuses, recommendations with separate judgment/rationale/
source facts/unknowns, and safe usage. It contains no channel-specific message or binding.

Migration `0004_weekend_packets` follows `0003_user_context`:
- `curation_jobs`: durable unique full-input identity, account/context/snapshot references,
  hashes, policy, running/success/partial/failed state, timestamps, safe failure/usage.
- `weekend_packets`: immutable validated JSONB and its hash, account and execution
  binding, pinned context/snapshot references, timestamp; one packet per execution.
- An additive context ID/account uniqueness constraint supports a composite FK that
  rejects another account's context. Packet composite FK binds account, execution,
  context and snapshot together. State constraints and triggers reject invalid
  transitions, terminal job mutation and packet mutation/deletion.

The stable SHA-256 curation identity includes account and the full canonical request
(including weekend, snapshot/context IDs and hashes, all policy/configuration inputs)
plus the actual prompt hash. A database unique insert commits the claim before the
provider call. Concurrent callers get an existing running/failure state or validated
completed packet; there is no duplicate provider execution or canonical packet.
No transaction is held during provider work. Context publication uses the same account
row lock as context updates and checks the active revision again. A changed context
fails that execution; its new immutable revision is eligible for a distinct packet.
Snapshot integrity is rechecked before publication. Failure never replaces prior packets.

Failures after a claim are persisted; missing/corrupt/oversized/incompatible inputs
before a claim return bounded unavailable outcomes without a job or provider call.
Cancelled calls are finalized as failed and cancellation propagates. A hard process
death can leave a running claim with unknown spend. It is deliberately not retried
automatically: recovery/reconciliation requires a future explicit operator policy.
A failed identical identity stays terminal. A materially revised context, snapshot
or reviewed configuration yields another identity; do not bump a revision as a hidden retry.

RLS has no client policies; PUBLIC and existing anon/authenticated grants are revoked.
Only a trusted backend role may use these records. Tests use disposable DB ownership.
Hosted role grants/policies need separate review; no hosted rollout is supplied.
Context and packet immutability is not protection against a privileged administrator
who can disable triggers; hashes detect accidental corruption, not malicious replacement
of all trusted state. Future erasure/retention must reconcile these references explicitly.

## Authenticated readback and delivery

`GET /api/me/packets/{packet_id}` uses the existing verified Supabase JWT identity.
There is no user selector and no generation route. Missing and foreign packets both
return bounded 404; absent/invalid authentication is 401, malformed IDs 422, corrupt
packets 503. All packet responses, including errors, carry `Cache-Control: no-store`.
CORS retains the existing GET-only policy for this resource. Logs use route templates.

The ID route is an explicit historical read, not a "newest means current" selector.
It revalidates payload/hash, account/job binding, policy/prompt, pinned context/snapshot,
and reconstructs the recommendations from research to detect altered facts even if a
packet hash was recomputed. A later context edit does not erase historical provenance.
Current-packet discovery needs a separate applicability selection policy. There is no
packet UI in this backend-only package.

Future delivery receives a persisted packet ID and an authorized recipient/channel
binding; it loads that same owned packet and renders it without recuration. Render all
source/context strings as untrusted text. Telegram can be the first development adapter;
email via Resend remains mandatory for V1. Verified binding, consent/entitlement,
outbox/delivery retries and actual sending remain separate. There is no owner identity,
hardcoded chat ID or privileged routing.

## Evidence and remaining work

The two-user test persists one synthetic universe directly, then uses the same service:
- Petaluma profile seeking a community workshop and participatory conversation selects
  `community-workshop`; rationale explicitly connects participation to the supplied
  workshop/social preferences.
- Santa Rosa profile seeking long ridge exploration selects `synthetic-ridge-route`;
  rationale connects outdoor exploration to the supplied long-route interest.
- Packets share snapshot ID/hash, pin distinct owned context revisions, survive
  independent reads, and deny signed cross-user requests and query/header spoofing.
  Regional rows/hashes are identical before/after. Shared worker/research entry points
  are forbidden and external HTTP is blocked in these tests. No WP3/WP4/WP5 invocation.

Additional tests cover simultaneous DB claims and replay, full/partial output, context
change during curation, missing/stale/incompatible/corrupt inputs, cancellation,
timeouts/malformed responses/extra fields, forged references, unknown/conflicting price
and availability, zero recommendations, incomplete usage, failed refresh preserving
history, RLS/immutability, foreign context FK rejection, and tampered packet facts.
Existing E0/E1 auth, API startup, PostgreSQL, security, isolation and scheduler gates
remain. The E2 checkout recognizes additive schema 0004; E1 checkout is unchanged and
the scheduler remains disabled.

Local validation: **809 Python passed, one expected hosted-Supabase skip; 39 web passed**.
Ruff format/lint, mypy (100 source files), CLI help, Alembic head/history and migration
roundtrip/metadata checks passed. Existing Starlette/cyclic regional-FK warnings remain.
The independent synthetic 0002 evidence stop/restart/export regression passed in its
isolated no-network container. Product Foundation CI explicitly requires the new packet
PostgreSQL proofs. Final SHA and exact-head CI are in the execution handoff.

Before a real ordinary-user proof: review curation quality and judgment vocabulary,
full-universe size/model limits and explicit model/pricing configuration, define claim
recovery, current-packet selection and retention, authorize real account/context and
a real provider call, review hosted migrations/backend roles, build owned web display,
then separately authorize verified Telegram delivery. Billing, Resend and external paid
acceptance remain governing obligations. No formal phase reconciliation is claimed.

Zero live AI/research calls, web searches, hosted migrations/writes, real accounts,
deliveries, schedule activation, deployment or merge. The retained October 16–18
development snapshot/database was neither opened nor modified.

## Exact changed files for this package

- `.github/workflows/product-foundation-ci.yml`
- `alembic/versions/0004_weekend_packets.py`
- `docs/e2-controlled-overlap-decision.md`
- `docs/e2-personalized-curation-packets.md`
- `src/event_radar/api/app.py`
- `src/event_radar/api/packets.py`
- `src/event_radar/db/models.py`
- `src/event_radar/db/packets.py`
- `src/event_radar/models/packet_validation.py`
- `src/event_radar/models/weekend_packet.py`
- `src/event_radar/services/curation_openai.py`
- `src/event_radar/services/packet_generation.py`
- `src/event_radar/services/personalized_curation.py`
- `src/event_radar/shared_schedule.py`
- `tests/conftest.py`
- `tests/test_api_shell.py`
- `tests/test_database_integration.py`
- `tests/test_shared_schedule_integration.py`
- `tests/test_weekend_packets.py`
- `tests/test_weekend_packets_integration.py`
