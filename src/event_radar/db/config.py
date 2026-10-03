"""Explicit backend configuration; never loads .env or personal settings."""

import os

from sqlalchemy.engine import URL, make_url


def database_url() -> URL:
    value = os.environ.get("DATABASE_URL")
    if not value:
        raise ValueError("Set backend-only DATABASE_URL before database operations.")
    return postgres_url(value)


def postgres_url(value: str | URL) -> URL:
    try:
        url = make_url(value)
    except Exception:
        raise ValueError("Invalid database URL.") from None
    if url.drivername != "postgresql+psycopg":
        raise ValueError("Use the postgresql+psycopg database driver.")
    return url
