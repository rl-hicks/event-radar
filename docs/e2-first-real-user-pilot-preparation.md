# E2 first real-user pilot preparation

Later security gate: [database remediation](e2-database-security-remediation.md)
adds revision 0006. The local init command now targets that hardened head; the
0005 descriptions below record the original proof, not current staging approval.

This is offline implementation evidence, not a real-user proof or acceptance of E1, E2, or Product V1. Starting commit: `af495cc99aa4e41e17ebdc9577d4118cc5bbb4a4`. E1 remains `26b454f41c3513de29f8e3a2bdada5f82185e421`; its activation gate and controlled overlap remain unchanged. No governing artifact was modified.

## Connected local proof

`docker-compose.e2.yml` provides a separate loopback PostgreSQL 17 database on port 55434, named `event_radar_e2_pilot`, with a dedicated persistent volume and synthetic-only development credentials. The guarded `python -m event_radar.pilot init` command applies additive migrations 0001–0005 only. Migration head remains `0005_packet_delivery`; this change requires no new migration. The CLI rejects libpq environment overrides and verifies database/user identity. Disposable destructive tests use the separate port-55432 database.

The integration test uses the normal FastAPI endpoints, established cryptographically signed JWT fixtures, database context and generation services, immutable packet reads, authenticated webhook boundary, and mocked Telegram HTTP adapter. It does not manually assemble a packet or add an application authentication bypass. The proof is ASGI/API plus React component testing, not a real hosted-auth browser session.

Latest local real-export proof produced packet `469b64bf-2b05-467a-b772-a093760e9838`: 107 opportunities, 265094 request bytes, 12 deterministic recommendations and four mocked Telegram messages. Context creation/update succeeded; a stale revision returned 409. Foreign-account context/packet reads returned 404; foreign bindings were empty. Current and historical viewing succeeded. A webhook without the secret returned 403, a valid synthetic update bound the destination, replay failed, duplicate dispatch did not resend, and revocation succeeded. Research rows remained unchanged and only one curation claim was created. Python socket connection/DNS guards rejected unintended outbound access, and the upstream research entry point was replaced with a failing guard.

## Public snapshot provenance and applicability

An existing verified public-only export was read from:

`/home/robot/dev/event-radar-e1-wp7/output/development-evidence/export-9c53c4de-3ec4-4634-a8d2-04242c113d1d-fe39ae23-9b41-4c16-9344-217c635d1c13.json`

- Envelope integrity hash: `76bce62f740bc917dd2584db09f31deac8b8586b1ff38a8759827c45f239b317`.
- Snapshot: `9c53c4de-3ec4-4634-a8d2-04242c113d1d`.
- Universe: `9147ab54-77dd-42ad-84ee-f6a7a19d2573`.
- Content hash: `1fcc03b832bd2fd2e9255ffe1c0f310fb0945017e528e72a0812a1aed6044e05`.
- Original policy: `e1-wp7-liveproof-2026-10-16-v1`; quality: `success`.
- Research as-of: October 11, 2026, 18:38:59.513327 Pacific; weekend October 16–18.
- Serialized universe: 263675 bytes, 82 events and 25 hikes.

The importer validates envelope/content hashes and schema, preserves original identities, research time, policy and quality, and rejects conflicting identities. Reimporting identical evidence is idempotent. Database insertion time is local because the export does not carry the original insertion timestamp. No retained E1 evidence database was accessed, modified, or re-exported.

`PACKET_RESEARCH_POLICY` explicitly selects either the existing default `e1-weekly-sonoma-v1` or the historical pilot policy. Both resolver and generation policy must select the same identity. There is no browser-controlled policy override or relabeling of research. Existing current-packet precedence and historical validation remain as documented in `e2-current-packet-and-delivery.md`.

The real snapshot passes the 500-opportunity/500000-byte input limits without truncation. At this proof's actual execution time it is fresh and targets the upcoming weekend. Under the unchanged 96-hour limit, it expires **October 15, 2026 at 18:38:59 Pacific**, before that weekend starts. After that deadline it is historical evaluation material only. A current pilot then requires separately authorized fresh regional evidence, not a freshness waiver or fabricated timestamp.

## Telegram scope correction

The subsequent owner decision supersedes Telegram product onboarding in this report. Telegram is a private development convenience; email remains required for public V1. The frontend connection panel and public challenge/config endpoints have been removed. Account-owned status/revocation and the verified binding/delivery domains remain. Use the explicit operator procedure in `e2-staging-readiness.md`; do not follow the original panel-based connection instructions below. Original offline evidence remains valid engineering history, not public feature acceptance.

## Ordinary product interfaces

The protected application now offers a compact profile editor: locality/timezone, interests and desired experiences first, expandable objectives, activities/exclusions, social/participation, solo/accessibility, travel/cost and recurring availability. Blank preferences remain unknown; untouched values are preserved. Saves use expected-revision concurrency checks; conflicts require reload. Changing locality clears stale coordinates. Saving refreshes current-packet applicability.

The Telegram panel shows connection state, explains delivery consent, creates an expiring in-memory challenge, displays `/start <challenge>`, refreshes status and revokes a binding. It never accepts a chat ID. The public bot handle comes from `TELEGRAM_PUBLIC_BOT_USERNAME`; absent configuration disables connection initiation. No bot credential enters the browser. Account/token-keyed components and cancellation prevent old profile, challenge or packet responses from appearing after account switch/sign-out. Responses remain private/no-store, without public payload storage.

## Inbound and outbound boundaries

`create_app(telegram_webhook_secret=...)` opts into a bounded webhook endpoint; the default application has no inbound route. It requires a constant-time-checked Telegram secret-token header before database access, limits bodies to 16 KiB, and accepts fresh nonforwarded `/start` messages from nonbot private-chat senders. Existing atomic challenge expiry/single-use/account and destination ownership rules remain authoritative. Secret values, chat identifiers and message content are not logged.

No polling or webhook registration was performed. Before any live use, inspect the existing bot's webhook/polling ownership with separate authority, coordinate its sole inbound consumer, establish a trusted HTTPS route and secure secret injection, and explicitly approve registration/update consumption. Current routing interference and actual webhook deployment have not been assessed. Reverse-proxy body/header logging must be disabled or redacted. The injected-secret boundary is implemented; operating infrastructure is not configured.

`TelegramHTTPTransport` is inert unless explicitly authorized and securely supplied a credential. It uses TLS, bounded socket timeouts and response size, no inherited proxy, redirects or automatic retry, and plain text messages within the provider UTF-16 limit. Success requires a valid message ID and matching destination. Definite 400/401/403/429 rejections are separated from ambiguous timeouts, malformed responses and 5xx outcomes.

Dispatch persists its claim before I/O and closes database transactions before every send. It rechecks binding/approval between chunks, caps message count at 16, and permits at most three attempts after definite first-message rejection. Success is idempotent; partial delivery, unknown result or interrupted sending requires reconciliation and never automatic redispatch. Revocation stops subsequent chunks but cannot recall an in-flight message. A socket timeout is not an absolute wall-clock execution guarantee.

The trusted operator may supply `PilotDeliveryAuthority` for one exact account, packet and binding, expiring within one hour. This is an explicit noncommercial pilot grant available for any ordinary account, not a paid entitlement or owner bypass. The approval reference/artifact must be retained by the operator; it is not a cryptographically signed or database-persisted approval ledger. Public requests cannot issue these grants. Commercial subscription eligibility remains unimplemented and live commercial cases fail closed. Existing binding revisions, durable intent/attempt records and packet/channel/binding idempotency remain in migration 0005.

## AI #3 preflight

Read-only preflight validates stored context, immutable snapshot/hash/quality/policy, research age and weekend, full input size, prompt/policy provenance and durable claim identity. Generation pins the reviewed context revision and rejects changes before provider execution. Existing one-call Responses adapter, timeout, persistence and idempotency remain in use; no curation policy or prompt tuning was performed.

An OpenAI run additionally requires secure credential injection and a model/pricing/capability review no older than seven days, including exact model, structured-output support, context window, positive input/output prices and a reviewed spending envelope no greater than $10. Estimated exposure is `(estimated_input_tokens * input_rate + max_output_tokens * output_rate) / 1000000`. The conservative byte-based planning estimate includes prompt/schema and framing reserve; it is neither an actual tokenizer result nor a hard billing cap. Actual exposure must be reviewed for the owner's final context and selected model. No current model price, capability or account access was verified offline; no dollar estimate is asserted as current pricing. The example policy stays deterministic and inert.

Existing incomplete/failed claims require reconciliation. Unknown usage remains unknown; an ambiguous provider result does not authorize a new claim/retry or a claim that no spend occurred. The operator must approve one call and a small exposure envelope, inspect the resulting persisted packet and usage, and stop on ambiguity.

## Repeatable offline commands

Run in the E2 worktree using the locked virtual environment. Docker permission may require an authorized local administrator.

```sh
docker compose -f docker-compose.e2.yml up -d --wait postgres_e2
.venv/bin/python -m event_radar.pilot init
.venv/bin/python -m event_radar.pilot import-snapshot --export "$PUBLIC_EXPORT" --expected-sha256 76bce62f740bc917dd2584db09f31deac8b8586b1ff38a8759827c45f239b317
E2_PILOT_LOCAL=1 E2_PILOT_EXPORT="$PUBLIC_EXPORT" E2_PILOT_EXPORT_SHA256=76bce62f740bc917dd2584db09f31deac8b8586b1ff38a8759827c45f239b317 .venv/bin/pytest tests/test_e2_pilot.py::test_connected_ordinary_user_pilot -q -s
```

Set `PUBLIC_EXPORT` to the reviewed path above. This test adds clearly synthetic account data and revokes its synthetic binding; it never uses a real account. Without those environment variables the test uses disposable PostgreSQL and deterministic synthetic research. Do not advance the clock or waive freshness to reuse the real export after expiry.

For a later authorized interactive local application, use the database URL from `docker-compose.e2.yml`, matching server `SUPABASE_URL`/`SUPABASE_PUBLISHABLE_KEY`, browser `VITE_SUPABASE_URL`/`VITE_SUPABASE_PUBLISHABLE_KEY`/`VITE_API_URL`, the approved local CORS origin, and explicit `PACKET_RESEARCH_POLICY`. Start the existing API and Vite development commands. Never set development authentication bypasses. Set only the public bot username for the panel; the default API still does not consume updates.

## Validation and remaining approval sequence

Local validation: 859 Python tests passed, one expected opt-in hosted Supabase test skipped; 59 frontend tests passed. Focused new pilot suite: 22 passed; combined pilot/delivery suites: 50 passed. Real-export isolated proof: one passed. Ruff formatting/lint, mypy (110 source files), frontend lint/typecheck/build, frontend security baseline and independent disposable evidence restart passed. Existing tests retain two-user packet isolation, stale context, partial quality, challenge spoof/group/expiry/reuse, concurrent idempotency, prompt evolution, ambiguous delivery and immutable shared research checks. New tests cover the connected flow, profile/challenge lifecycle, account-switch races, mocked HTTP classification, approval scope, revocation between chunks, policy selection, preflight blockers and pinned context. Product Foundation CI now requires the connected PostgreSQL proof and inter-chunk revocation case. See the final handoff for exact-head CI and final SHA.

The owner reported Supabase unpaused, but no public project URL/publishable key was available in the inspected public configuration. Actual availability, JWT/JWKS/signing configuration, redirect URLs and account readiness remain unverified. No service-role key is needed. The pilot can retain a local application database; hosted database migrations are not a prerequisite for that architecture. Choosing hosted persistence would require separate migrations/RLS/grants review and approval.

Ordered first-real-user procedure, each live operation requiring the stated separate approval:

1. Supply public Supabase configuration and complete a read-only connectivity/JWKS/auth configuration assessment. Confirm normal browser redirect/CORS settings. Approve any necessary hosted configuration change or real account provisioning separately; neither is authorized by this report.
2. Approve use of the isolated local application for real private data, its access/retention controls, and normal Supabase sign-in. The owner enters/confirms their own context through the profile editor; never import legacy private context. Stop synthetic fixture runs against a database containing real private data.
3. Select the reviewed public snapshot and exact research policy. Re-run freshness, weekend and full-input checks at execution time. If expired, obtain a separately authorized current snapshot. Do not activate the weekly scheduler implicitly.
4. Review an exact Responses model, capability/context limits, current pricing and a small one-call spending envelope. Supply a reviewed policy file and `PricingReview` JSON. Run `python -m event_radar.pilot preflight --snapshot-id ... --policy ... --pricing-review ...` using a hidden ordinary-account access token. The read-only command intentionally reports credentials missing; final executable preflight runs after secure credential injection.
5. Explicitly approve **one real AI #3 call** for that account/context/snapshot and exposure envelope. Run the same CLI `curate` command with `--execute-approved`; supply credentials only at the hidden prompt. Check the persisted packet, current/historical web presentation and usage. Stop on ambiguous failure; do not regenerate to retry delivery.
6. Use the operator-managed linking procedure in `e2-staging-readiness.md` (the former product connection panel is removed). Separately approve bot credential access and routing inspection, the coordinated HTTPS webhook configuration and live update consumption. Securely inject the webhook secret, register only after checking historical polling/webhook interference, and have the operator issue a challenge with the consenting ordinary account's verified access token, then have that user send it privately to the bot. This constitutes a real binding and requires explicit approval.
7. Review the exact packet and verified binding. Explicitly approve **one Telegram delivery**, with an operator approval JSON containing `approval_reference`, `user_id`, `packet_id`, `binding_id`, `issued_at`, and `expires_at` (at most one hour). Run `python -m event_radar.pilot deliver --packet-id ... --binding-id ... --approval ... --execute-approved`, supplying the ordinary access token and bot credential through hidden prompts. Inspect durable intent/attempt results; reconcile partial/unknown delivery manually before any further send.
8. Confirm receipt and ordinary web access, retain the approval/evidence securely, and agree on shutdown/revocation and retention. No public launch, paid recurrence, E1 acceptance, E2 acceptance or Product V1 readiness follows from one pilot.

This assignment made zero live OpenAI calls, Telegram sends/update-consumption operations, hosted Supabase operations, research collection calls or real account/binding creations. GitHub synchronization/CI and local Docker/test operations are separate engineering operations.

## Exact changed files

- `.github/workflows/product-foundation-ci.yml`
- `src/event_radar/api/app.py`
- `src/event_radar/api/config.py`
- `src/event_radar/api/delivery.py`
- `src/event_radar/api/packets.py`
- `src/event_radar/db/delivery.py`
- `src/event_radar/services/packet_delivery.py`
- `src/event_radar/services/packet_generation.py`
- `tests/test_packet_delivery_integration.py`
- `web/src/Foundation.tsx`
- `web/src/styles.css`
- `config/e2-pilot-policy.example.json`
- `docker-compose.e2.yml`
- `docs/e2-first-real-user-pilot-preparation.md`
- `src/event_radar/api/telegram_inbound.py`
- `src/event_radar/db/curation_preflight.py`
- `src/event_radar/db/snapshot_import.py`
- `src/event_radar/models/delivery_authority.py`
- `src/event_radar/pilot.py`
- `src/event_radar/services/telegram_transport.py`
- `tests/test_e2_pilot.py`
- `web/src/PilotInterfaces.test.tsx`
- `web/src/ProfileEditor.tsx`
- `web/src/TelegramConnection.tsx`
- `web/src/api/private.ts`
