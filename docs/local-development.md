# Local development foundation

The personal research CLI, product API, and browser shell coexist in this repository.
WP1 adds structure only: no product routes (including `/health`), authentication,
user tables, migrations, or frontend data requests exist yet. The API does not
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

Both commands are empty in WP1 because there are no revisions. Future work will add
models, import them into `alembic/env.py`, and use the following commands only after
reviewing generated migrations:

```bash
uv run alembic revision --autogenerate -m "Describe schema change"
uv run alembic upgrade head
```

No `create_all` runs on application startup. Offline migration plumbing can be
checked without a database using `uv run alembic upgrade head --sql`; with no
revisions this produces no product schema.

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
