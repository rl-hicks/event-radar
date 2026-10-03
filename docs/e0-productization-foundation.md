# E0 productization foundation

This note documents the repository-side foundation introduced during E0. It is execution
evidence, not a governing artifact.

## Existing personal path

The existing `event-radar` CLI remains `event_radar.main:main`. Its GitHub Actions production
workflow remains separate from the public API/web runtime. Importing
`event_radar.api.app` does not invoke `event_radar.main.execute`, Telegram polling, research,
or packet delivery.

## Public API

Local API:

```bash
uv run uvicorn event_radar.api.app:app --reload
```

Foundation endpoints:

- `GET /health` — unauthenticated service/database health.
- `GET /api/me` — authenticated identity -> `app_users` database roundtrip.

The backend derives the user UUID only from a validated Supabase JWT. A client-supplied user ID
is not an authorization input.

## Local database

```bash
docker compose up -d postgres
uv run alembic upgrade head
```

Migrations are authoritative. Application startup does not auto-create schema.

## Web

```bash
cd web
npm ci
npm run dev
```

The E0 routes are `/`, `/login`, `/signup`, and protected `/app`. The shell deliberately
does not implement onboarding, packets, subscriptions, or later product behavior.

Browser-safe variables:

- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`
- `VITE_API_URL`

Backend-only variables include `DATABASE_URL` and any legacy `SUPABASE_JWT_SECRET`.

## Current E1 coupling note

The existing personal pipeline is still single-user by design:

- `event_radar.main._build_current_pipeline` loads one filesystem `UserContext`;
- it loads one private personal-experience preference document;
- permanent and temporary Telegram directions come from filesystem state;
- `build_recommendation_pipeline` carries that user/personal context through the pipeline;
- AI #1 receives the scraped-event-analysis projection of private preference context;
- AI #2 receives the web-discovery projection and uses the current user's base location;
- final recommendation context receives the final-curation projection and current directions.

E1 must separate reusable regional intelligence from these per-user inputs without replacing the
working collectors, normalization/deduplication, weather, hike, provider-fallback, audit, or
telemetry behavior unnecessarily.

## Deployment seams

- Render blueprint: repository root `render.yaml`.
- Vercel SPA routing: `web/vercel.json`.
- Supabase supplies PostgreSQL and Auth.

Actual staging provisioning and deployed verification remain external E0 gates.
