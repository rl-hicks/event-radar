# Local development foundation

The personal research CLI, product API, and browser shell coexist in this repository.
WP3 adds service health and an identity-foundation API on migration-managed
persistence. Real authentication and frontend API requests are not implemented.
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
`GET /api/me` returns 401 until WP4 supplies real authentication.

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

Open the local URL Vite prints; stop with Ctrl-C. This page only identifies the
product as under development. It has no API requests or account features.

```bash
npm run lint
npm run typecheck
npm test -- --run
npm run build
```

No browser environment variables are currently required. Future `VITE_*` values
are public browser configuration. Never place backend credentials, `DATABASE_URL`,
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

`GET /api/me` obtains identity exclusively from `get_current_user()`. This dependency
always returns 401 with `WWW-Authenticate: Bearer` in WP3, even for supplied bearer
tokens. No token is parsed or trusted. Supabase JWT verification belongs to WP4.
Only tests override the dependency with synthetic `AuthenticatedUser` objects;
there is no runtime bypass flag, test token, or identity header.

When tests provide an identity, the route gets or creates its UUID `app_users` row
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
tests are not live PostgreSQL proof. No browser auth or product UX is included.
