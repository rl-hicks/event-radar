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

## Verification

```bash
uv run ruff format .
uv run ruff check .
uv run mypy src
uv run pytest
git diff --check
```
