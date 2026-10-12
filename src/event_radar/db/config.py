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


def research_database_url(value: str) -> URL:
    url = postgres_url(value)
    if (
        not url.host
        or not url.username
        or not url.password
        or not url.database
        or url.port is None
        or not 1 <= url.port <= 65535
        or url.port == 6543
        or set(url.query) - {"sslmode"}
    ):
        raise ValueError("Explicit direct/session PostgreSQL target is required.")
    local = url.host in {"localhost", "127.0.0.1", "::1"}
    if not local and url.query.get("sslmode") != "verify-full":
        raise ValueError("Remote research PostgreSQL requires sslmode=verify-full.")
    if local and url.query.get("sslmode") not in (None, "disable", "require", "verify-full"):
        raise ValueError("Unsupported local PostgreSQL SSL mode.")
    return url
