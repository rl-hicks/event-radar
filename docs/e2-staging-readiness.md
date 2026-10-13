# E2 scope correction and staging readiness

Security gate update: [database remediation](e2-database-security-remediation.md) and
[hosted execution runbook](e2-database-security-runbook.md) supersede this historical
checklist's 0005 target. Hosted staging now requires separately approved hardening through 0006.

Baseline: `ba7c96082605f7ce38b20db2b9832028fde8aac6`, branch `e2/first-user-vertical-slice`. The exact new candidate SHA and its CI run are reported in the implementation handoff; use that full SHA for both manual deployments, not a moving branch tip. No hosted inspection, deployment or migration occurred. Existing Render/Vercel deployment SHAs and URLs are unknown; the owner's report that Supabase is unpaused is not independent availability evidence. E1/E2 remain incomplete.

## Product scope and operator-only Telegram linking

Telegram is a private development delivery convenience. Email remains mandatory for public Product V1; this change does not implement Resend or commercial delivery. The ordinary `/app` has profile editing and packet viewing, with no Telegram panel, bot handle, challenge or onboarding. `/api/me/delivery/telegram/challenge` and `/api/me/delivery/telegram/config` are removed (404 even with a valid token). Read-only binding metadata and account-scoped revocation remain for privacy/control; neither discloses destinations or creates bindings. There is no public dispatch endpoint.

The existing challenge verification, atomic consumption, private-chat identity checks, destination non-transferability, revocation, packet renderer and delivery audit/transport remain unchanged. The standard Render factory never enables the optional Telegram webhook.

After separate approval for a private development link, the operator runs in a private interactive terminal against the existing isolated local pilot database:

```sh
.venv/bin/python -m event_radar.pilot telegram-link --approve-private-development-link
```

The consenting ordinary account supplies its current access token at a hidden prompt. The existing Supabase verifier determines account ownership; there is no account-ID or chat-ID selector, hardcoded identity, new auth authority or auth bypass. Operator process/DB access and the explicit flag establish execution authority; they are not commercial entitlement. The account must already exist through normal authenticated application use. The command prints one short-lived `/start` challenge only to an interactive terminal; do not record, redirect or log it. The user sends it to the operator-confirmed existing bot. Only the separately authorized authenticated inbound adapter can consume it after private-chat/sender/expiry/single-use checks. The command does not read bot credentials, start polling, register a webhook, consume updates or send Telegram messages.

Use the existing authenticated GET `/api/me/delivery/bindings` for redacted status and POST `/api/me/delivery/bindings/{id}/revoke` to revoke, supplying the same normal bearer token. Ownership is enforced server-side. Challenge issuance alone proves neither Telegram control nor delivery authorization. A separate packet/account/binding-scoped delivery grant is still required.

The operator CLI intentionally remains local-database-only. If the owner chooses a hosted staging database for the genuine pilot, the CLI does not silently follow its DATABASE_URL: a separately reviewed hosted operator runner targeting that exact database is a blocker. Do not link in one database and expect it to appear in another. The shortest existing private-delivery path remains the isolated local pilot, while hosted staging can first validate auth/profile/viewing independently.

## Reviewed repository configuration

- `render.yaml`: changed from the stale E0 branch to E2; auto deployment remains off. Python 3.13.14, uv 0.11.28, `uv sync --frozen --no-dev`; start `.venv/bin/uvicorn event_radar.api.app:create_app --factory --host 0.0.0.0 --port $PORT --no-access-log`. No migration/startup research/provider calls. Health `/health` checks database connectivity (`SELECT 1`), not schema presence, the full 0005 schema or auth.
- `web/vercel.json`: repository root directory must be `web`; Vite, Node 24, `npm ci`, `npm run build`, output `dist`, SPA rewrite. Vercel branch/domain/autodeploy settings are hosted settings not proven by this file. Review/disable automatic deployment before pushing an authorized release; importing this repository is not authorized here.
- Supabase Auth is the sole JWT authority. Server requires issuer `<SUPABASE_URL>/auth/v1`, audience `authenticated`, valid UUID subject/role, expiry. ES256/RS256 verify against that project's JWKS. Legacy HS256 calls authoritative `/auth/v1/user` and then enforces claims; no local shared signing secret. Auth traffic requires future connectivity approval and matching public server/browser project configuration.

## Exact environment inventory

| Target | Variable | Required value/constraint |
| --- | --- | --- |
| Render | DATABASE_URL | Secure backend-only SQLAlchemy psycopg URL from the verified Supabase Connect dialog; session pooler 5432 for IPv4, not transaction pooler 6543; verified TLS settings. Never guess credentials/host or put this in Vercel. |
| Render | SUPABASE_URL | Exact existing project's HTTPS origin; no path. |
| Render | SUPABASE_PUBLISHABLE_KEY | Current `sb_publishable_` public key for that same project, not service role. |
| Render | SUPABASE_JWT_AUDIENCE | `authenticated`. |
| Render | WEB_ORIGINS | Exact stable staging Vercel HTTPS origin, no path/wildcard; empty until reviewed origin is known. |
| Render | PACKET_RESEARCH_POLICY | Default `e1-weekly-sonoma-v1`; explicit historical pilot option `e1-wp7-liveproof-2026-10-16-v1` only when consuming that unchanged snapshot. |
| Render | PYTHON_VERSION / UV_VERSION | Blueprint pins above; PORT is supplied by host. |
| Vercel | VITE_SUPABASE_URL | Same public project origin as Render. |
| Vercel | VITE_SUPABASE_PUBLISHABLE_KEY | Same public publishable key. |
| Vercel | VITE_API_URL | Exact authorized Render HTTPS origin, no path. Rebuild after changes. |

No Telegram bot credential, bot handle, webhook secret, OpenAI credential, owner ID, private context, DB password or service-role key belongs in the browser. The public API needs no Telegram/OpenAI credentials. Do not copy the legacy personal environment. No provider environment values were read or changed here.

Signup uses Supabase's default Site URL, with no custom emailRedirectTo. Review Site URL and exact confirmation redirect allowlist for the stable staging domain, preserving unrelated authorized destinations. Do not disable confirmation or broaden to wildcard preview origins. Existing confirmed-user password login may require no URL change; verify before requesting changes. CORS is not authentication.

## Ordered staging checklist (not execution authorization)

1. Record the approved full E2 candidate SHA and green exact-head Product Foundation CI. Record current Render/Vercel deployment SHAs, project/service IDs, stable URLs, branch/autodeploy configuration and rollback commits using separately authorized read-only hosted inspection. Do not assume they run E2. Keep automatic deployments off.
2. Obtain public Supabase URL/key and approve read-only project/auth/JWKS/connectivity and database revision/privilege assessment. Record actual project availability, signing algorithm, DB target and connectivity from the intended runtime. No public URL/key is presently available in checked configuration. Do not create accounts or call `/api/me` as a read-only database check: that route can insert the app-user row.
3. Choose isolated staging data location and retention/backups. Obtain separate approval for schema/permission changes. Inspect current Alembic revision before any migration; stop on unknown schema conflicts and never stamp/downgrade to hide them. Use a reviewed migration role, not browser keys. Migration order: `0001_app_users` → `0002_regional_universes` → `0003_user_context` → `0004_weekend_packets` → `0005_packet_delivery`. After authorization, run `alembic upgrade 0005_packet_delivery` explicitly and verify `alembic current`; never migrate during Render builds/startup/health checks. No new migration is introduced by this correction.
4. Review effective hosted grants and RLS, including provider default privileges. 0003 enables RLS and revokes PUBLIC on context revisions; 0004 additionally revokes existing anon/authenticated grants on packets and curation jobs; 0005 does so on all four delivery tables. These tables have no browser policies. Inspect 0001/0002 legacy app-user/research exposure separately: those migrations do not establish equivalent RLS for all earlier tables. This is a hosted readiness gate, not a claim that all historical tables are protected. Audit schema/table grants and default grants to PUBLIC/anon/authenticated; approve any remediation separately. The backend uses direct database access, so verify runtime role grants and owner/RLS behavior for required operations without giving browsers backend access. Owner/bypass-role access does not itself prove least privilege. Verify immutable triggers and foreign keys too.
5. Configure reviewed backend values securely. After deployment approval, manually deploy the exact candidate to Render and record deployed SHA. Verify truthful `/health`, 401 unauthenticated `/api/me`, and schema head separately. No auth-account creation at this step.
6. Configure Vercel's stable staging branch/domain and three public build values. After approval, manually deploy the same SHA; record source SHA/build result. Update Render's exact CORS origin only with configuration approval. Apply any required Supabase redirect changes only with explicit approval. Verify direct `/`, `/login`, `/signup`, `/app`, unknown route and static assets; test allowed/disallowed CORS origins.
7. Separately approve ordinary account provisioning/sign-in and application writes. The user enters their own context in the normal UI. Verify revision conflicts, sign-out/account switch, no private payload storage, no-store packet responses and account isolation. No real account was created in this assignment. Hosted viewing needs an authorized persisted packet in the same backend DB; do not substitute fake evidence for real-user proof.
8. Follow the preserved first-real-user runbook for explicit snapshot import, preflight, one AI call, packet review and optional private Telegram development delivery. Keep email as the public V1 requirement. Never activate the scheduler, deploy a webhook, or send merely because staging checks pass.

## Research and minimum live approvals

The October 16–18, 2026 public export retains snapshot `9c53c4de-3ec4-4634-a8d2-04242c113d1d` and original research policy. Its 96-hour freshness expires October 15 at 18:38:59 Pacific. Do not relabel or refresh its timestamps. After expiry it supports historical evaluation only; a genuinely current pilot requires a separately authorized fresh snapshot. The retained E1 evidence DB remains untouched; no export or connected proof needs repeating for this scope correction.

Minimum outstanding decisions/approvals are: (a) read-only hosted status/configuration assessment and exact URLs/SHAs; (b) chosen staging database plus reviewed migration/grant changes, manual Render/Vercel deployments and any redirect/CORS changes; (c) real ordinary-account provisioning/sign-in and private-data retention; (d) selected applicable snapshot/import, or fresh research if expired; (e) reviewed model/pricing/exposure envelope and one genuine AI #3 call; (f) only if private Telegram delivery is wanted, bot credential/routing inspection, coordinated trusted inbound setup/live update consumption, operator challenge linking with account consent, and one exact packet/binding delivery approval. The local pilot can omit hosted deployment/migration approvals if explicitly chosen instead; hosted staging and private local delivery must not be presented as one connected hosted proof.

No AI #3 philosophy, prompt, ranking or schema changes. Binding domain/adverse-case tests remain; the deterministic integration now obtains its challenge through the authenticated operator boundary and verifies removed product routes return 404. Frontend tests retain profile/account-switch protection and assert no Telegram UI. Full test/CI results and final SHA are in the handoff.
