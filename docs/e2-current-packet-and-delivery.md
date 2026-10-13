# E2 current packet viewing and offline delivery foundation

Status: bounded offline implementation for execution-lead review. E1, E2 and Product V1
remain unaccepted. The owner's Current Packet Viewing & Telegram Delivery Foundation
assignment extends the earlier controlled overlap specifically to this package. It overrides
prior package-specific delivery exclusions, not accepted governing requirements. No accepted
governing artifact is changed. Formal PM reconciliation remains pending.

Baseline: `8e5e07e447445ac36926d119bb5c6c6e2201abd3`, clean and synchronized local/remote
`e2/first-user-vertical-slice`, `/home/robot/dev/event-radar-e2`. E1 remains stacked at
`26b454f41c3513de29f8e3a2bdada5f82185e421`; draft PR #2 is not modified or merged.
Final SHA and exact-head CI evidence are reported in the execution handoff.

## Current applicability and deterministic precedence

`GET /api/me/packets/current` is registered before the historical UUID route. Both use
E0 verified JWT identity, backend account scoping, bounded errors and `Cache-Control: no-store`,
including error responses. Reads never create accounts, contexts, packets, jobs or research.

The small explicit service policy is Sonoma County (`sonoma-county-ca`), timezone
`America/Los_Angeles`, research identity policy `e1-weekly-sonoma-v1`, matching the existing
shared research envelope. Every account uses this same initial service region; locality text
is not interpreted as eligibility, coordinates or a region. Tests explicitly inject the
synthetic research policy and aware clock. No arbitrary region selection or geocoding exists.
Monday–Thursday selects the coming Friday; Friday–Sunday selects that active Friday.
Monday at local midnight advances the window. DST follows the region's IANA timezone.

Selection joins account-owned packet rows to their pinned regional snapshot and regional
identity for that Friday and research policy. Each candidate undergoes historical readback
validation. Foreign packets and previous weekends are excluded. Snapshot facts, hashes,
context ownership, execution identity, status and reconstruction must all validate. A corrupt
candidate or future-dated research returns unavailable; corruption never silently falls back
to a different candidate. Missing research identity or no completed packet is not_generated;
a failed job with no persisted candidate is unavailable. A running claim without a packet is
not_generated. Failed refreshes do not erase an intact candidate.

Descending precedence is:
1. Context revision number (newer preferences first).
2. Combined success before partial quality within that context revision.
3. Research as-of timestamp.
4. Packet creation timestamp.
5. Packet UUID as a stable tie-break.

The selected packet always retains its original snapshot ID/hash and context ID/hash.
The response is current when that context matches the active revision, otherwise older_context
with the active context revision separately exposed. It does not claim older preferences are
current. `degraded` is true for partial quality, research older than the packet's recorded
freshness bound, or a superseded snapshot. Separate research_stale and snapshot_superseded
flags explain those cases. Full-quality older research can outrank partial newer research;
the supersession/freshness warnings make that intentional tradeoff visible. No packet is
invented. Historical lookup remains available after context edits or weekend expiry.

## Version-aware historical integrity

The v1 prompt and v1 result validator are retained explicitly in packet_validation.py.
`historical_validator` accepts only the exact policy version, prompt version and immutable
v1 prompt hash. Readback computes curation identity using the recorded, allowlisted prompt
hash and reconstructs recommendations with the retained v1 validator. It does not consult
the active `PROMPT` alias. Unsupported versions/hashes and corrupted content remain rejected.
A regression simulates a later deployment changing the active prompt and validator: intact
v1 packets still read using v1 validation. Future policy/schema support requires an explicit
reviewed addition; arbitrary record-supplied hashes are never accepted as policy authority.
No judgment vocabulary, prompt text, ranking strategy or provider behavior was changed.

## Authenticated web viewing

The existing protected `/app` page displays the current packet after the existing backend
identity check. It retains the E0 auth flow and identity diagnostics. Packet requests obtain
the bearer token from the authenticated Supabase client and verify the expected session account.
The component keys/displays results by account and token, cancels pending requests on changes,
and ignores late responses after cleanup/timeouts. Foreign response account IDs are rejected.
No packet is written to localStorage, sessionStorage or another public cache. Signout unmounts
private content. Loading, missing, older-context, degraded, unauthorized and error/retry states
are explicit. No browser research or curation calls exist.

Recommendations preserve stored order, rationale, tradeoffs, factual locations, occurrences,
price quotes (including conflicts), access/attendance observations, route facts, supported
semantic descriptions, unknowns and source links. Strings are React text, never HTML. Source
links require HTTPS without credentials and use noopener/noreferrer and no referrer. Backend
canonical evidence URL validation remains authoritative. Missing end times, unscheduled hikes,
unknown prices and availability stay unknown. A recommendation is not a booking assertion.

## Verified binding and privacy

Authenticated routes:
- POST /api/me/delivery/telegram/challenge: initiates connection and delivery consent; returns
  a 256-bit cryptographic bearer challenge once, valid for ten minutes, with no-store.
- GET /api/me/delivery/bindings: own IDs, channel, revision, status and consent only; no chat ID.
- POST /api/me/delivery/bindings/{binding_id}/revoke: own binding only; foreign IDs return 404.

Only SHA-256 of the high-entropy challenge is persisted. Issuing a replacement invalidates
outstanding challenges. A trusted inbound adapter must authenticate Telegram transport before
calling accept_private_update. There is deliberately no HTTP inbound endpoint, polling,
webhook registration, bot configuration, credential lookup or live transport in this package.
Synthetic trusted updates prove the domain boundary; they are not proof of live Telegram
transport authentication. An ordinary web client cannot submit a destination to bind it.

Acceptance requires a private chat, a non-bot positive integer sender equal to the private
chat ID, an existing unexpired unconsumed challenge, and its owning account. The token selects
the account; inbound callers cannot substitute an account UUID. Account/row locks atomically
consume the challenge and revoke/replace the previous binding. A destination advisory lock
serializes competing accounts. A destination previously used by another account is rejected,
even after revocation; ownership transfer needs a future separately reviewed recovery flow.
New binding rows increment per-account/channel revisions; old rows cannot change destination.
Revocation clears consent and invalidates outstanding challenges. No owner-specific path exists.

## Additive migration and durable outbox

`0005_packet_delivery` follows 0004 and adds delivery_bindings, delivery_challenges,
delivery_intents and delivery_attempts, plus packet ID/account uniqueness for composite FKs.
RLS is enabled with no client policies, PUBLIC/anon/authenticated grants revoked where present.
Identifiers remain backend-only. There are no bot credentials or plaintext challenge columns.
Hosted backend-role grants and privacy/retention/erasure policy still require review.

Bindings have unique active account/channel and destination/channel constraints, immutable
revision identity and revocation history. Composite FKs enforce packet and binding ownership.
A unique (packet ID, channel, binding ID) identifies one intent: binding ID is the immutable
revision, so a verified replacement creates a distinct destination intent. Triggers protect
binding revisions, single-use challenge transitions, retained intents and terminal attempts.
They do not protect against an administrator who can disable triggers.

queue_delivery accepts authenticated account + persisted packet ID + verified binding revision
+ channel. It checks account ownership, active status, consent and full packet readback.
Success and explicitly labelled partial packets qualify in development. Explicit historical
packet IDs are allowed by this internal foundation; it is not a recurring current-week sender.
There is no public queue/dispatch route. Development must be explicitly enabled; unsupported
commercial/live entitlement always fails closed. No fake subscription constitutes entitlement.

States are pending -> sending -> sent / failed / ambiguous; revoked blocks dispatch. Each
transport attempt is retained separately, with count and bounded failure code. Claim commits
before sending. Sending claims left by crashes are not retried. Binding locks recheck and
serialize revocation/rebinding immediately around fake sends. This lock-across-send design is
bounded to offline fakes; a live worker needs reviewed timeout/transaction handling.

Definitive rejection before any message can retry explicitly up to three attempts. Prior
success is never resent. Failure after a successful chunk, timeout/unknown response, invalid
response or unknown provider outcome is ambiguous and cannot automatically retry. No exactly-once
external-delivery claim is made. Ambiguous/sending reconciliation is deliberately operator-only
and not implemented as an automated recovery path. Delivery failures never regenerate research
or AI #3, nor mutate a packet or shared snapshot.

## Telegram adapter and future email contract

render_telegram accepts the validated persisted canonical packet and emits plain text,
without Markdown/HTML parse mode, preserving names, source facts, dates, locations, reasons,
tradeoffs and important unknowns. Messages are capped at 3,900 UTF-16 units, including emoji;
long text splits without dropping content. No independently curated Telegram packet exists.
The fake transport takes destination + rendered message and returns success, definitive
rejection or ambiguity. Other outcomes fail closed as ambiguous. Raw provider data/errors,
private messages, tokens and chat identifiers are never logged or persisted as diagnostics.

The dispatcher accepts only the concrete FakeTelegramTransport with explicit development
eligibility. It cannot load a live client via configuration. Tests inject deterministic
outcomes, including multi-message partial failure. The eventual channel adapter contract is:
owned persisted packet + verified active binding -> channel renderer -> bounded transport
outcome -> durable attempt. A Resend email adapter must consume the same packet, require a
verified address/consent and actual entitlement, and preserve the same idempotency/reconciliation
semantics. Email remains mandatory for Product V1; no Resend operations are implemented.

## Evidence and limitations

Focused new Python integration module: 28 tests. Combined with migration roundtrip/lifecycle:
30 tests. Final local full suite: **837 passed, one expected hosted-Supabase skip**.
The existing 809 Python cases remain covered. Exact-head CI is supplied in the handoff.
Web: 52 tests, including 13 new packet tests. Coverage includes two users, cross-account API
spoofing, foreign response rejection, delayed browser responses, signout, safe URLs/text,
previous weekends, older contexts, quality/freshness precedence, superseded snapshots,
missing/corrupt packets, prompt evolution, expired/reused/replaced/spoofed/group/bot challenges,
destination theft rejection, concurrent consumption and queue/dispatch, revocation, retries,
ambiguous sends, interrupted claims, Unicode limits, immutable audit and RLS isolation.
Regional row/hash equality and unchanged curation counts prove delivery causes no regeneration.
New integration tests forbid external HTTP; fake delivery contains no network calls.

Required gates include format/lint/mypy, full disposable PostgreSQL suite, migration metadata
roundtrips, frontend lint/typecheck/tests/build/security, tracked-source security, CLI help,
and the existing independent no-network synthetic evidence restart/export regression at 0002.
Only the opt-in hosted Supabase test is expected to skip. CI explicitly requires new delivery
PostgreSQL tests. Existing Starlette and cyclic regional FK metadata warnings remain.

Before any live proof: separate owner/execution-lead authorization; reviewed account/context
provisioning and hosted migrations/scoped backend roles; authenticated Telegram inbound transport
and bot identity/credential management; challenge abuse controls and user-facing connection UX;
a bounded live outbound transport and crash/ambiguity reconciliation; commercial entitlement
for paid use; privacy/retention operations. Real AI #3 curation and delivery each need explicit
approval. Deeper personalization remains deferred. Resend, Stripe, external paid-user evidence,
E1 acceptance and formal phase reconciliation remain outstanding.

Zero live Telegram/OpenAI/Supabase/Resend/weather/research provider calls, real accounts or
bindings, hosted operations, deliveries, scheduler activation, deployment or merge. GitHub
branch synchronization, the authorized push and CI evidence are repository operations only.
Retained October 16 research evidence and historical bot secrets were not accessed.

## Changed files

- `.github/workflows/product-foundation-ci.yml`
- `alembic/versions/0005_packet_delivery.py`
- `docs/e2-current-packet-and-delivery.md`
- `src/event_radar/api/app.py`
- `src/event_radar/api/cors.py`
- `src/event_radar/api/delivery.py`
- `src/event_radar/api/packets.py`
- `src/event_radar/db/current_packet.py`
- `src/event_radar/db/delivery.py`
- `src/event_radar/db/models.py`
- `src/event_radar/db/packets.py`
- `src/event_radar/models/packet_validation.py`
- `src/event_radar/services/packet_delivery.py`
- `src/event_radar/shared_schedule.py`
- `tests/conftest.py`
- `tests/test_api_shell.py`
- `tests/test_database_integration.py`
- `tests/test_packet_delivery_integration.py`
- `tests/test_shared_schedule_integration.py`
- `web/src/Foundation.test.tsx`
- `web/src/Foundation.tsx`
- `web/src/PacketView.test.tsx`
- `web/src/PacketView.tsx`
- `web/src/api/packets.ts`
- `web/src/styles.css`
