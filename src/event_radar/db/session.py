"""Lazy engine construction and explicit transaction-scoped sessions."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

from event_radar.db.config import postgres_url


def build_engine(url: str | URL) -> Engine:
    """Construct a pool without connecting; callers own engine.dispose()."""
    return create_engine(
        postgres_url(url),
        pool_pre_ping=True,
        pool_timeout=5,
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=5000"},
    )


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Commit on success, roll back on error, and close in either case."""
    with factory.begin() as session:
        yield session
