# E2 User Context foundation

Base: E1 `26b454f41c3513de29f8e3a2bdada5f82185e421`.
Scope authority: [controlled overlap decision](e2-controlled-overlap-decision.md).
The historical `models/user_context.py` remains unchanged and is not loaded by
the product API. Its rigid profile identifiers, mandatory detailed policies and
private-file runtime are unsuitable defaults for a minimal public profile.

## Product schema

`models/product_context.py::ProductUserContext` uses schema version
`user-context-v1`. The only required user-supplied object is `base_location`
with locality and valid IANA timezone. Coordinates are optional and must be
supplied as a pair; no geocoding, precision inference or default home base occurs.

Optional fields cover interests, activity preferences, exclusions, desired
experiences, objectives, social/participation preferences, accessibility
constraints, novelty, solo considerations, travel modes/time/tradeoffs, cost
amount/currency/tradeoffs, recurring local availability and output preferences.
All unspecified optional fields are null, not inferred personal attributes.
An explicitly empty list means the user supplied no items, not unknown.

Texts are trimmed, nonempty, at most 400 characters; lists have at most 20 items,
availability at most 21 same-day windows. Travel/cost/count bounds reject invalid
values; amounts require currency; recurring availability uses the base timezone.
Cross-midnight availability must be split across days. Free-text preferences
remain untrusted data for future AI #3, never tool instructions. No user UUID,
chat destination, entitlement, arbitrary metadata or Weekend Intent is accepted
inside the context. Extra fields and unknown schema versions are rejected.
A future Weekend Intent contract is separate; no weekly overrides are stored here.

## Migration, history and concurrency

`0003_user_context` follows `0002_regional_universes` and adds only
`user_context_revisions`, an append-only table containing:

- revision UUID; authenticated `app_users.id` FK;
- positive per-account sequence, unique with the account UUID;
- schema version, validated JSONB, canonical JSON SHA-256;
- timezone-aware creation timestamp for that immutable revision.

The active context is the highest committed per-account sequence. Revision 1's
timestamp is context creation; the active revision's creation timestamp is the
last context update time. No mutable duplicated head pointer or history deletion
endpoint is needed. Every successful update creates a new revision, including a
same-content save; older revisions remain available to future packet provenance.
A hash checks integrity, not authenticity or encryption.

Writers revalidate the full model, ensure the E0 identity row exists and lock that
account row. They then compare the caller's expected revision UUID with the
current revision and append atomically. Concurrent creation yields one winner;
concurrent updates from the same revision yield one winner and a 409 conflict.
No last-write-wins overwrite. Failed validation occurs before any identity or
context insert; transactional failures roll back.

Database triggers reject UPDATE/DELETE of revisions. Administrative migrations
can still drop tables; this is not an immutable backup against an administrator.
RLS is enabled without client policies and PUBLIC table grants are revoked:
Supabase/browser roles have no direct context access even with a later SELECT
grant. No account deletion/erasure lifecycle is implemented in this package;
future privacy/retention work must explicitly reconcile revision retention and
packet provenance with authorized erasure.

The trusted backend performs explicit account-scoped SQL using the verified JWT.
Offline tests use the disposable database owner. Before any hosted rollout,
review actual schema/default grants and a scoped backend-role access policy;
a non-owner role with no RLS policy will fail closed. Do not grant blanket
BYPASSRLS or expose context through Supabase Data API as a workaround.
No hosted access/role configuration is established here.

The E2 branch's scheduler recognizes the known compatible 0002 and additive 0003
revisions, rejecting unknown history and performing no migration. The original
E1 checkout stays unchanged. The restart regression explicitly migrates its
synthetic public-evidence database to 0002, so it does not add private context
tables to an evidence-only environment.

## Authenticated API

All routes use E0 Supabase JWT verification and authentication-first, function-
scoped database sessions. Identity comes only from verified JWT `sub`.
There is no arbitrary-user context route. A supplied account query/header cannot
select another account; account fields in request JSON are rejected.

| Method/path | Body | Result |
| --- | --- | --- |
| GET /api/me/context | none | 200 active revision, or bounded 404 |
| POST /api/me/context | full ProductUserContext | 201 initial revision; 409 if already created |
| PUT /api/me/context | `expected_revision_id`, full `context` | 200 new revision; 409 if stale, foreign or missing base |

Updates replace the whole document; omitted optional fields become unknown.
Clients must read and preserve fields they intend to retain. No PATCH semantics
or silent merge is implied. Response includes revision ID/sequence, revision
creation timestamp, content hash and context. It carries `Cache-Control: no-store`.

Missing/invalid auth is 401; malformed data 422; conflict 409; database or corrupt
stored-context failures are bounded 503. Responses/logs never echo validation
inputs, SQL exceptions, JWTs or private bodies. Request logs retain route template,
method, status and duration. CORS allows GET/POST/PUT and Authorization/Content-Type
only on the context route for configured web origins; E0 routes retain GET-only CORS; no cookie credentials or wildcard origin.
No frontend, real account, subscription or delivery sender is added.

## Isolation and verification

Tests use fake cryptographic JWT signers/JWKS with actual E0 verification and
disposable PostgreSQL. They prove two distinct contexts, foreign revision denial,
query/header spoof resistance, invalid/service-role token denial, no-auth denial,
history, concurrent initial creation/updates, immutability, RLS client denial,
revalidation, corrupt-read safety and bounded logging.

A synthetic WP7 universe is persisted; context writes/readback leave all regional
rows and hashes unchanged with zero additional research calls. A second fake
regional run, after private contexts exist, queries no context table and sends
no private markers to semantic or discovery planning inputs. Existing WP8
two-consumer, provenance, import-isolation and E0 security suites remain required.

Run tests only with the existing guarded `TEST_DATABASE_URL` disposable target.
Never point fixtures at retained evidence or hosted databases. Product Foundation
CI retains every prior PostgreSQL/restart gate and adds required E2 context cases;
the E2 branch push trigger provides exact-head CI without altering draft E1 PR #2.
No migration has been applied to the retained 0002 evidence database or Supabase.

## Next package, not implemented

See [delivery and AI #3 boundary](e2-delivery-and-curation-boundary.md).
The next bounded engineering package should pin a shared snapshot and context
revision, validate AI #3 recommendation references, and persist the canonical
personalized packet with provenance and ownership. Deterministic tests should
precede separately authorized real curation/delivery. This package creates no
entitlement bypass and does not establish E1/E2 acceptance.

## Verification handoff

Local full Product Foundation-equivalent checks passed: **754 Python tests**,
one expected opt-in hosted Supabase skip, **39 web tests**. The 25 new context
tests include signed two-user API access, simultaneous initial creation, concurrent
updates, immutable history, invalid/corrupt data, RLS and regional isolation.
Ruff format/lint, mypy (93 source files), tracked-source security, frontend
lint/typecheck/build/security, CLI help and Alembic metadata checks passed.
The independent 0002 evidence database restart/readback/export regression passed.
Existing Starlette deprecation and regional cyclic-FK metadata warnings remain;
there are no new private-value serializer warnings.

The final implementation SHA and exact-head CI run are supplied in the execution
handoff. No governing artifact, E1 branch/worktree, preserved real snapshot,
hosted resource, real account or delivery secret was modified. All database
writes/migrations were to disposable synthetic PostgreSQL instances.
