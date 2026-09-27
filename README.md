# Event Radar

Event Radar collects Sonoma County weekend events, evaluates a curated North Bay hike
catalog against trailhead weather, and uses a three-stage OpenAI pipeline to prepare a
high-signal ChatGPT decision packet.

The automated curation layer preserves optionality; it does not choose a final itinerary.
The owner's private Telegram conversation receives a compact summary and the full Markdown
packet as a document.

Every factually valid, deduplicated scraped event reaches semantic analysis. A separate
Responses API web-search stage can add verified weekend events, and the final curator sees
the resulting unscored event cards alongside hikes, weather, directions, and user context.
The legacy deterministic event scorer remains available only as an audit diagnostic.

## Requirements

- Python 3.13
- `uv`
- Telegram bot credentials for one owner/private-chat conversation
- An OpenAI API key for semantic event analysis, web discovery, and final curation

If an AI stage is unavailable, Event Radar reports that fallback explicitly. Scraped-event
analysis failure preserves broad factual event cards; web-discovery failure adds no web events.

## Setup

```bash
uv sync
cp .env.example .env
cp config/user_context.example.json config/user_context.json
```

Configure `.env`, then customize the private, gitignored `config/user_context.json` profile.
The committed example documents the schema without publishing the real profile.

Set `TELEGRAM_OWNER_USER_ID` to the owner's Telegram user ID and `TELEGRAM_CHAT_ID` to that
owner's private conversation with the bot. Inbound `/temp ...` and `/permanent ...` commands
are accepted only when both IDs match and Telegram reports the chat type as `private`.
Addressed forms such as `/temp@bot_username ...` remain compatible but are not required in
the private conversation. Keep `.env` private; it is gitignored.

Run the normal Telegram direction-polling and digest flow with:

```bash
uv run event-radar
```

Generated ChatGPT packets are written under the gitignored `output/` directory.

Run the same read-only pipeline locally, without polling or sending Telegram or mutating
direction state, with:

```bash
uv run event-radar --audit
```

The audit writes gitignored stage artifacts under `audit/<weekend-Friday>/`. Add
`--no-llm` to inspect factual collection, legacy diagnostics, hikes, weather, and a broad
factual context without making any OpenAI calls.


## Production on GitHub Actions

The public application repository runs production ephemerally on a GitHub-hosted runner.
Private runtime configuration and mutable state live separately in the private
`rl-hicks/event-radar-state` repository. The workflow checks out that repository into an
ignored runtime directory using a token scoped only to the private state repository.

Configure these Actions secrets on the public repository:

- `EVENT_RADAR_STATE_TOKEN`
- `OPENAI_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TELEGRAM_OWNER_USER_ID`

The private state repository is the production source of truth for
`config/user_context.json`, `config/personal_experience_preference_context.md`, and the three
`state/*.json` files. At runtime, the workflow copies those files into the application's
normal paths without printing their contents.
It runs the locked quality checks and the existing `uv run event-radar` CLI. Telegram
remains the only delivery mechanism for the private summary and Markdown decision packet.

After the application and complete Telegram delivery succeed, only the Telegram offset,
permanent directions, and temporary directions are copied back and committed to the private
state repository. The user context and personal preference policy are read-only, generated
packets remain ephemeral, and application failures do not persist partially updated state.

The `Event Radar` workflow runs automatically every Thursday around 12:15 PM
America/Los_Angeles, while `workflow_dispatch` remains available for manual runs. Two UTC
cron entries account for PDT/PST; the lightweight guard intentionally skips the entry that
does not match the current Pacific UTC offset. GitHub-hosted scheduled workflows may start
later than the nominal cron time without being rejected by the guard.

## Private personalization and curation shape

The private state repository supplies both `config/user_context.json` for structured runtime
facts and `config/personal_experience_preference_context.md` as the canonical AI taste policy.
Neither real file is committed to this public repository.

Final curation normally targets roughly 12-18 worthwhile events, with flexible underflow on
weak weekends and modest overflow on unusually rich weekends. Independent self-directed hikes
are additive and do not consume event slots. Guided hikes discovered through event sources
remain events.

## Verification

```bash
uv run ruff format .
uv run ruff check .
uv run mypy src
uv run pytest
git diff --check
```
