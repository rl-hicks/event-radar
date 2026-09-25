# Event Radar

Event Radar collects Sonoma County weekend events, evaluates a curated North Bay hike
catalog against trailhead weather, compresses both inventories deterministically, and uses
an automated OpenAI research-editor pass to prepare a high-signal ChatGPT decision packet.

The automated curation layer preserves optionality; it does not choose a final itinerary.
The owner's private Telegram conversation receives a compact summary and the full Markdown
packet as a document.

## Requirements

- Python 3.13
- `uv`
- Telegram bot credentials for one owner/private-chat conversation
- An OpenAI API key for automated curation (the deterministic fallback works without one)

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
`config/user_context.json` and the three `state/*.json` files. At runtime, the workflow
copies those files into the application's normal paths without printing their contents.
It runs the locked quality checks and the existing `uv run event-radar` CLI. Telegram
remains the only delivery mechanism for the private summary and Markdown decision packet.

After the application and complete Telegram delivery succeed, only the Telegram offset,
permanent directions, and temporary directions are copied back and committed to the private
state repository. The user context is read-only, generated packets remain ephemeral, and
application failures do not persist partially updated state.

The `Event Radar` workflow is intentionally `workflow_dispatch`-only. Weekly scheduling will
be enabled only after a successful manual cloud verification.

## Verification

```bash
uv run ruff format .
uv run ruff check .
uv run mypy src
uv run pytest
git diff --check
```
