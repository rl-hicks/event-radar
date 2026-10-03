# Local development foundation

The personal research CLI, product API, and browser shell coexist in this repository.
WP2 adds migration-managed identity persistence only. No product routes (including
`/health`), authentication, or frontend data requests exist yet. The API does not
import the personal runtime configuration or require private files or a database.

Use a separate development worktree. Do not copy production `.env`, personal
context, Telegram state, or credentials into it. Commands below run from the
repository root unless stated otherwise.

## Python and API

Use uv with Python 3.13 (`.python-version`):

```bash
uv sync --frozen
uv run event-radar --help
uv run uvicorn event_radar.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

The API starts an empty ASGI application; requests currently return 404. Stop it
with Ctrl-C. No health route is needed to prove startup.

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
uv run pytest tests/test_database_integration.py -v
sudo docker compose -f docker-compose.test.yml down
unset TEST_DATABASE_URL
```

Always run the final `down` command even if a test fails. No `-v` is needed. This
command targets only the test project; it leaves development containers and the
persistent `event-radar-dev_postgres_data` volume untouched.

The integration suite verifies base-to-head, head-to-base-to-head, reflected schema,
model/migration drift, connectivity, identity insert/read, distinct UUIDs, transaction
rollback, and returned connections. Cleanup downgrades the test schema to base.
Without `TEST_DATABASE_URL`, these two tests explicitly skip; skips are not PostgreSQL
verification evidence. With it set, connection or safety failures fail the tests.

For a development database, `DATABASE_URL` plus `uv run alembic current` reports the
applied revision. Do not run `downgrade base` on valuable data: it drops `app_users`.
Avoid `docker compose down -v`, volume pruning, and manual schema creation.
