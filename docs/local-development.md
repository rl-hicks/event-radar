# Local development foundation

The personal research CLI, product API, and browser shell coexist in this repository.
WP4 adds Supabase user-token validation and a development browser auth check
on migration-managed identity persistence. This is not Product V1.
The API does not import personal runtime configuration or require private files.
Startup does not require a configured/reachable database.

Use a separate development worktree. Do not copy production `.env`, personal
context, Telegram state, or credentials into it. Commands below run from the
repository root unless stated otherwise.

## Python and API

Use uv with Python 3.13 (`.python-version`):

```bash
uv sync --frozen
uv run event-radar --help
uv run uvicorn event_radar.api.app:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

The API starts without connecting to PostgreSQL. Stop it with Ctrl-C.
`GET /health` returns 200 when the configured DB responds, otherwise 503.
`GET /api/me` requires a validated Supabase access token. Missing tokens return 401;
unconfigured/provider-unavailable authentication returns a sanitized 503.

The existing `uv run event-radar` command remains the personal production runner.
It requires private context/state and credentials, performs research, polls Telegram,
and may deliver messages. Do not run it as a development smoke. Even
`--audit --no-llm` fetches external sources and writes audit artifacts.

## Browser shell

Use Node 24 or newer (`web/.nvmrc` selects Node 24) for the web toolchain.

```bash
cd web
npm ci
npm run dev
```

Open the local URL Vite prints; stop with Ctrl-C. This page identifies the product as under development and provides a minimal
reusable auth check, without final routing or product features.

```bash
npm run lint
npm run typecheck
npm test -- --run
npm run build
```

An unconfigured browser shows setup guidance. Configure the public `VITE_*` values
in `web/.env.local` to enable Supabase auth and API calls. Never place backend credentials, `DATABASE_URL`,
OpenAI keys, Telegram tokens, or service-role secrets in them. See `web/.env.example`.

## Local PostgreSQL and future migrations

Docker Engine with Compose is required for the database commands:

```bash
docker compose up -d postgres
docker compose ps
```

Wait for `healthy`. PostgreSQL 17 is bound only to localhost port 5432, with database
and user `event_radar` and development-only password `event_radar_local`. A named
volume persists data. These credentials are local examples, never production values.

Alembic reads `DATABASE_URL` from the process environment only; it does not read
`.env` or legacy settings. The example root `.env.example` documents this backend-only
variable; exporting it is required for database operations:

```bash
export DATABASE_URL='postgresql+psycopg://event_radar:event_radar_local@127.0.0.1:5432/event_radar'
uv run alembic heads
uv run alembic history
```

The initial head is `0001_app_users`. Apply reviewed migrations explicitly; API
startup never applies them. Future model changes must also be registered in
`alembic/env.py`. Review generated migrations before applying them:

```bash
uv run alembic revision --autogenerate -m "Describe schema change"
uv run alembic upgrade head
```

No `create_all` runs on application startup. Offline migration plumbing can be
checked without a database using `uv run alembic upgrade head --sql`; this renders
SQL without executing it. Online migration commands require a running database.

Stop the local database while retaining its volume:

```bash
docker compose down
```

Do not add `--volumes` unless intentionally deleting local database data.

## Python verification

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
git diff --check
```

The API isolation test runs in a fresh subprocess and empty directory, blocks
legacy imports, network connections, private state access, and writes, and exercises
ASGI startup/shutdown. It requires no production credentials. The existing production
workflow is unchanged; no product deployment or new CI workflow is provided by WP1.

## WP2 persistence boundary

`db.config.database_url()` reads only process-level `DATABASE_URL` when called.
`build_engine(url)` creates a lazy PostgreSQL/Psycopg engine; no connection occurs
on import or construction. It sets five-second connection/pool timeouts and a
five-second statement timeout. Callers dispose their engine when finished.
`build_session_factory(engine)` and `session_scope(factory)` provide commit on
success, rollback on exception, and session closure. `check_database(engine)` is
an internal `SELECT 1` check returning a boolean, not an HTTP endpoint.

`app_users` contains only caller-supplied UUID `id` and required timezone-aware
`created_at`/`updated_at`. Both timestamps default to PostgreSQL `now()` on insert.
There is no UUID generation, automatic update trigger, or ORM `onupdate` behavior.
Future writers must set `updated_at` explicitly when updates are introduced.
Alembic exclusively owns schema creation; no runtime `create_all` exists.

## Isolated PostgreSQL integration tests

`docker-compose.test.yml` is a separate project (`event-radar-test`), with only
`postgres_test`, localhost port 55432, database/user `event_radar_test`, and disposable
tmpfs storage. It never mounts the development volume. Test data is lost when the
container stops. Do not use this service for durable development data.

Tests opt in through `TEST_DATABASE_URL`, never through `DATABASE_URL`. Before any
connection, a guard requires the exact PostgreSQL/Psycopg driver, 127.0.0.1, port
55432, test database/user, and no URL query overrides. Inherited libpq `PG*`
environment overrides are removed for the test. A live database/user check
and an unexpected-table guard precede destructive migrations. The fixtures replace
`DATABASE_URL` only within tests and reset only the dedicated test schema.
Do not run these destructive integration tests concurrently against one test service.
Never forward a remote/production database into this reserved local test port.

Owner-run verification (use sudo if needed; authenticate in your terminal):

```bash
cd /home/robot/dev/event-radar-e0
sudo docker compose -f docker-compose.test.yml up -d --wait --wait-timeout 90 postgres_test
sudo docker compose -f docker-compose.test.yml ps
sudo docker compose -f docker-compose.test.yml exec -T postgres_test pg_isready -U event_radar_test -d event_radar_test
export TEST_DATABASE_URL='postgresql+psycopg://event_radar_test:event_radar_test_local@127.0.0.1:55432/event_radar_test'
uv run pytest
sudo docker compose -f docker-compose.test.yml down
unset TEST_DATABASE_URL
```

Always run the final `down` command even if a test fails. No `-v` is needed. This
command targets only the test project; it leaves development containers and the
persistent `event-radar-dev_postgres_data` volume untouched.

The integration suite verifies base-to-head, head-to-base-to-head, reflected schema,
model/migration drift, connectivity, identity insert/read, distinct UUIDs, transaction
rollback, and returned connections. Cleanup downgrades the test schema to base.
Without `TEST_DATABASE_URL`, the PostgreSQL tests explicitly skip; skips are not PostgreSQL
verification evidence. With it set, connection or safety failures fail the tests.

For a development database, `DATABASE_URL` plus `uv run alembic current` reports the
applied revision. Do not run `downgrade base` on valuable data: it drops `app_users`.
Avoid `docker compose down -v`, volume pruning, and manual schema creation.

## WP3 API contracts and authentication boundary

`GET /health` is unauthenticated. With a working `DATABASE_URL` it returns
`{"status":"ok","database":"ok"}`. Missing/invalid configuration or failed
connectivity produces 503 with unavailable status and a sanitized error envelope.
It checks `SELECT 1`; it does not validate migration currency, create schema, or
run migrations. WP2 engine timeout settings bound connection/pool/statement waits.

`GET /api/me` obtains identity exclusively from `get_current_user()`. WP4 validates
Supabase user tokens before constructing identity; arbitrary bearer strings, user
IDs, and API keys are not authentication. Tests may override the identity dependency
or use ephemeral signed tokens, but there is no runtime bypass flag or test token.

With a validated identity, the route gets or creates its UUID `app_users` row
and returns `id`, identity-provided `email`, `created_at`, and `database_roundtrip`.
Email is never persisted. Query/body/header user IDs have no effect. PostgreSQL
`ON CONFLICT DO NOTHING` handles competing inserts; subsequent lookup uses the
normal READ COMMITTED isolation level. Function-scoped DB dependency teardown
commits before sending success, rolls back failures, and closes the session.
Engines are created lazily per application and disposed at shutdown.

`WEB_ORIGINS` is a backend-only comma-separated list of exact HTTP(S) origins,
with no paths, credentials, or wildcards. Default: `http://localhost:5173`.
An empty value allows no cross-origin access. If browsing Vite at 127.0.0.1,
explicitly include `http://127.0.0.1:5173`. Only GET and the Authorization request
header are enabled; cookie credentials are disabled. CORS is not authentication.

API errors use `{"error":{"code":"...","message":"..."}}`. Health failure also
includes `status` and `database`. Validation responses do not echo request input.
Raw database/provider errors and tracebacks are never returned. CORS preflight
rejections are handled by the standard CORS middleware.

The `event_radar.api` logger emits JSON request records containing method, matched
route template (or `<unmatched>`), status, duration_ms, and error_code. It omits
query strings, raw unmatched paths, bodies, authorization headers, tokens, user
context, database URLs, exception text, and traceback locals. Use the documented
`--no-access-log` Uvicorn flag to avoid its separate raw URL access logs. CORS
preflight requests are handled before route request logging.

The API/PostgreSQL integration tests use the guarded disposable fixture from WP2
and synthetic auth to prove A/B persistence, repeat identity, manipulation resistance,
health, and concurrent identity creation. Run the complete suite with
`TEST_DATABASE_URL` exported using the owner workflow above; skipped integration
tests are not live PostgreSQL proof. WP4 adds only a development auth surface; final routing and product UX remain later work.

## WP4 Supabase authentication

Backend configuration is read from process environment only (not legacy `.env`):

```text
SUPABASE_URL
SUPABASE_PUBLISHABLE_KEY
SUPABASE_JWT_AUDIENCE=authenticated
```

Set the matching public browser configuration in ignored `web/.env.local`:

```text
VITE_SUPABASE_URL=
VITE_SUPABASE_PUBLISHABLE_KEY=
VITE_API_URL=http://localhost:8000
```

Use current `sb_publishable_` keys. These keys identify an application component,
not a user, and are safe to distribute in the browser. Secret keys, legacy
service-role keys, database passwords, and shared JWT signing secrets are forbidden
in browser configuration. This implementation requires no such privileged key.
URLs require HTTPS except explicit localhost/127.0.0.1 development endpoints.
`VITE_API_URL` is optional and defaults to `http://localhost:8000`.
Keep `WEB_ORIGINS` aligned with the actual Vite origin.

The backend intentionally supports ES256 and RS256 via the configured project's
`/auth/v1/.well-known/jwks.json`. PyJWT performs signature, expiration, issuer,
audience, and subject validation. Required role is `authenticated`, subject must be
a UUID, and issuer must exactly match `<SUPABASE_URL>/auth/v1`. The token's header
only selects an allowlisted mechanism; remote key URLs supplied by tokens are ignored.
PyJWT caches JWKS for five minutes (no permanent per-key cache), uses five-second
network timeouts, and bounds forced refreshes with its default cooldown. Configuration
and verifier construction perform no network I/O. Key rotation may require the
library's refresh cooldown/cache interval; invalid tokens never fail open.

HS256 compatibility uses GET `/auth/v1/user` with the publishable `apikey` header
and the user's bearer token, with a five-second timeout and no redirects. No shared
JWT secret is stored or used. Only after Auth accepts that exact token do we enforce
issuer/audience/expiry/role/UUID policy and compare subject to the authoritative user
ID. Email comes from the Auth response. Failed asymmetric verification never falls
back to this path. Malformed or rejected tokens return 401; unavailable configuration
or providers return sanitized 503. `/health` remains only API/database connectivity.

Browser sign-up/sign-in use email/password through the official Supabase JS client.
Session persistence and automatic refresh use the SDK defaults explicitly enabled.
Sign-out uses `scope: 'local'`, leaving unrelated browser/device sessions alone.
The API client obtains the current access token and sends only Authorization Bearer,
never an owner/user ID. Tokens and passwords are not rendered or logged.

The reusable auth component stays on the development page; no `/login`, `/signup`,
or `/app` route architecture is introduced. If sign-up returns no session, the UI
asks the user to confirm email. Do not disable project confirmation policy or use
admin credentials to bypass it. Use owner-confirmed staging accounts for testing.

### Owner-controlled live verification

Provide a staging project with the current publishable key and two distinct confirmed
email/password users. Do not commit credentials or place them in shell history.
Export backend variables above plus these test-only environment variables using your
normal secure terminal setup:

```text
SUPABASE_TEST_USER_A_EMAIL
SUPABASE_TEST_USER_A_PASSWORD
SUPABASE_TEST_USER_B_EMAIL
SUPABASE_TEST_USER_B_PASSWORD
```

Start only the disposable PostgreSQL service using the earlier owner workflow, export
`TEST_DATABASE_URL`, then run `uv run pytest --tb=short`. The opt-in real-auth test
signs in existing A/B users, checks `/api/me`, repeat row identity, distinct rows, and
attempted B-to-A impersonation. It creates no Supabase users and changes no user
metadata or project settings. Sensitive real-auth failures suppress traceback details.
Without staging credentials, the real-auth test explicitly skips. Without the test
DB, both signed-fixture and real-auth PostgreSQL proofs skip. Skips are not evidence.
Always shut down the test project afterward without deleting development volumes.

For manual browser proof, migrate the local development database explicitly, export
backend auth/database configuration, start Uvicorn with `--no-access-log`, and start
Vite with its public configuration. Sign in as A, check `/api/me`, sign out locally,
then repeat as B. Capture only UUIDs/status, never passwords, tokens, or API key values.
Email confirmation remains owner-controlled. Local browser proof and real staging
proof are distinct from mocked component tests.

No deployment is part of WP4. WP6 must still prove the deployed chain:
web -> Supabase Auth -> FastAPI -> PostgreSQL, including deployed origins/configuration,
A/B isolation, refresh, and local-session sign-out. No E0 deployment claim is made here.
