# Event Radar

Event Radar gathers local event listings, normalizes them into a common
schema, ranks them against user preferences, and delivers a personalized
weekly digest through Telegram.

## Initial scope

The first version will:

- collect events from one source
- normalize event data
- filter events within a specified date range
- format a basic digest
- deliver the digest through Telegram

LLM ranking, multiple sources, persistence, and scheduling will be added after
the first end-to-end pipeline works.

## Requirements

- Python 3.13
- uv
- Telegram bot credentials

## Setup

```bash
uv sync
cp .env.example .env