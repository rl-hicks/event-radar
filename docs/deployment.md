# E0 staging deployment (WP6)

This is foundation-only staging, not Product V1. Configuration in Git is not proof
of deployment. WP7 CI and all personal production behavior remain outside this work.
Do not deploy from main. Use `codex/e0-wp6-deployment-foundation` and record the exact
commit deployed by both providers. No provider resources or credentials are in Git.

## Owner prerequisites and authorization

1. Sign in to Render and Vercel in an owner-controlled browser. Authorize access only
   to `rl-hicks/event-radar` as needed. Do not paste tokens into chat.
2. Review free/staging eligibility and account limits. The Render Blueprint explicitly
   selects `free`; stop if either provider requires a paid commitment. Do not upgrade.
3. Use the existing Supabase project dashboard. Rotate BOTH exposed staging-user
   passwords before any A/B proof. Supply replacements only via secure runtime entry;
   never reuse old passwords, commit them, or record them in logs/screenshots.
4. Obtain database access through Supabase Connect as described below. Keep password
   and credential-bearing URLs in secure local/provider configuration only.

No authenticated Render/Vercel access was available during repository preparation.
Hosted migration, URLs, logs, routes, and A/B evidence must be recorded after access.

## Supabase database and explicit migrations

Render runtime uses **Shared Pooler / Session mode** because it needs IPv4 connectivity.
Copy the exact connection URI from the project's **Connect** dialog, selecting session
mode (5432). Never guess the pooler hostname or provider-specific username. Do not use
transaction mode (6543) or assume the IPv6 direct endpoint is reachable from Render.
Change only the URI scheme to `postgresql+psycopg://`; retain the supplied host, user,
port, database, encoded password, and connection options. Use provider-recommended
TLS settings. `DATABASE_URL` is backend-only and must never enter Vercel or VITE_*.

Migrations run explicitly from an authorized owner environment, never API startup,
Render builds, or health checks. Prefer direct connectivity when the owner network
supports it; otherwise use the provider-supported session pooler with Alembic's
NullPool. Do not use the disposable-test fixture or downgrade commands on Supabase.
Verify the target project before exporting DATABASE_URL securely. Do not echo it.

```bash
cd /home/robot/dev/event-radar-e0
uv sync --frozen
uv run alembic heads
uv run alembic history
# With the reviewed migration-safe DATABASE_URL securely exported:
uv run alembic current
uv run alembic upgrade head
uv run alembic current
```

Expected head/current: `0001_app_users`. If existing tables/revisions conflict, stop;
do not stamp over them or manually create schema. Review migration exceptions locally
before sharing output: database driver diagnostics can contain connection details.
No changes to auth.users or other Supabase-managed schemas are permitted.

Safe read-only SQL in the authorized Supabase SQL editor can verify the result:

```sql
SELECT version_num FROM public.alembic_version;
SELECT to_regclass('public.app_users');
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'app_users'
ORDER BY ordinal_position;
```

Expect id UUID primary key and non-null created_at/updated_at timestamptz. No other
product tables are introduced. After the A/B browser proof, query only those known
UUIDs (replace placeholders with the two verified non-secret identifiers):

```sql
SELECT id FROM public.app_users
WHERE id IN ('USER_A_UUID'::uuid, 'USER_B_UUID'::uuid)
ORDER BY id;
```

Expected: two distinct rows. Do not inspect unrelated auth records or credentials.

## Render API

Create a new Blueprint from the WP6 branch using root `render.yaml`. Check that the
name does not refer to an unrelated existing resource. Service: `event-radar-api-staging`.
Root directory: repository root. Native Python, pinned Python 3.13.14 / uv 0.11.28.
No Render-managed database, frontend install, paid disk, or paid pre-deploy command.

Build:

```sh
uv sync --frozen --no-dev
```

Start:

```sh
.venv/bin/uvicorn event_radar.api.app:create_app --factory --host 0.0.0.0 --port $PORT --no-access-log
```

Render provides uv for uv.lock projects. The runtime uses the built environment
without dependency resolution or migration. Manual deploys are intentional for WP6.
Health path is `/health`; the final deployment requires configured DB connectivity.
A missing DB gives truthful 503 and will not satisfy the configured health check.
Do not remove that check to claim successful deployment.

Set these backend environment variables in Render (sync:false prompts on creation):

- DATABASE_URL: exact reviewed session-pooler URL, SQLAlchemy scheme.
- WEB_ORIGINS: final exact Vercel HTTPS origin, no path or wildcard. Before that
  origin is known, use an empty value to grant no cross-origin browser access.
- SUPABASE_URL: existing staging project URL.
- SUPABASE_PUBLISHABLE_KEY: current publishable key, not service-role/secret.
- SUPABASE_JWT_AUDIENCE: authenticated (Blueprint default).

Do NOT import the personal .env wholesale. Never set OPENAI_API_KEY,
TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, or TELEGRAM_OWNER_USER_ID on this API service.
After migrations/configuration, manually deploy and record the HTTPS onrender.com URL.

## Vercel web

Create a NEW `event-radar-web-staging` project from the same repository and WP6 branch.
Set the project's production branch to WP6 for its stable staging domain (Vercel's
"Production" label is a hosting environment, not Event Radar Product V1 or main).
Verify the chosen branch before the initial deploy; if import defaults to main,
change it before deploying or explicitly select the WP6 branch deployment.

Root Directory: `web`; framework: Vite; Node: 24.x; install: `npm ci`; build:
`npm run build`; output: `dist`. `web/vercel.json` declares these commands and the
SPA rewrite to index.html. Direct routes and unknown paths reach React Router;
real static assets must continue serving with their proper content types.

Set ONLY these public build-time values in the environment used by this deployment:

- VITE_SUPABASE_URL
- VITE_SUPABASE_PUBLISHABLE_KEY
- VITE_API_URL: deployed Render HTTPS origin, no path.

Never configure DATABASE_URL, database passwords, secret/service-role keys, JWT
shared secrets, or test-user passwords in Vercel. Rebuild if VITE_* values change.
Record the stable HTTPS Vercel origin. Set Render WEB_ORIGINS to exactly that origin
and redeploy Render. Do not automatically allow changing preview origins or `*`.

## Supabase Auth URL settings

In Auth URL Configuration, inspect existing Site URL and redirect allowlist first.
For a staging-dedicated project, set Site URL to the exact stable Vercel HTTPS origin
and allow only required exact confirmation destinations. The current signup uses
Supabase's Site URL default (no custom emailRedirectTo). Preserve any known required
local URLs; do not replace unrelated applications' configuration without review.
Keep email confirmation policy unchanged. Existing confirmed-user password login
does not depend on changing that policy. Never disable confirmation to pass a test.

## Deployed acceptance evidence

After owner authorization and password rotation, capture only status, UUIDs, URLs,
and commit IDs. Never record passwords, bearer/refresh tokens, or provider key values.

1. Render /health: HTTP 200, status ok, database ok, no configuration data.
2. Unauthenticated /api/me: 401, sanitized envelope, WWW-Authenticate Bearer.
3. OPTIONS /api/me with the exact web Origin and requested GET/Authorization:
   matching ACAO. With an unrelated origin: no permissive ACAO. CORS is not auth.
4. Direct HTTPS browser navigation to /, /login, /signup, /app and an unknown path:
   expected page or guard; unknown renders application not-found, not provider 404.
5. Sign in A with rotated credentials, verify backend UUID matches A, API confirmed,
   database_roundtrip=true. Refresh /app; restoration works. Sign out; /app protected.
6. Sign in B with rotated credentials; distinct UUID and database confirmation.
   Visit /app?user_id=<A UUID>: backend identity remains B. Sign out; /app protected.
7. Run the restricted A/B row query above. Verify two distinct app_users UUIDs.
8. Inspect browser console for material auth/config errors without copying tokens.
9. Inspect Render build/runtime logs for ordinary Uvicorn startup only. Confirm no
   research, Telegram, OpenAI, private-state mutations, URL/password/key dumps,
   Authorization headers, or tokens. Review privately; redact before sharing.

Do not generate destructive failures. Free-service cold starts may need waiting;
repeat health checks before browser verification rather than weakening auth/timeouts.
If free-tier constraints cannot meet a mandatory gate, stop for owner decision.

The carried WP4 deployed chain is satisfied ONLY after actual evidence of:
Vercel web -> Supabase Auth -> Render FastAPI -> Supabase PostgreSQL.
Local tests, config validation, and prior local browser proof do not substitute.
No WP7 workflow or Product V1 capability is added here.

## Provider references

- https://render.com/docs/blueprint-spec
- https://render.com/docs/uv-version
- https://render.com/docs/python-version
- https://vercel.com/docs/frameworks/frontend/vite
- https://supabase.com/docs/guides/database/connecting-to-postgres
