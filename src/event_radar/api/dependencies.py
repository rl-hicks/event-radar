"""Lazy, application-owned DB resources and authentication-first sessions."""

from collections.abc import Iterator
from threading import Lock
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from event_radar.api.errors import DatabaseUnavailable
from event_radar.auth.identity import AuthenticatedUser, get_current_user
from event_radar.db.config import database_url
from event_radar.db.health import check_database
from event_radar.db.session import build_engine, build_session_factory, session_scope


class DatabaseResources:
    def __init__(self) -> None:
        self._engine: Engine | None = None
        self._lock = Lock()

    def engine(self) -> Engine:
        with self._lock:
            if self._engine is None:
                self._engine = build_engine(database_url())
            return self._engine

    def close(self) -> None:
        with self._lock:
            if self._engine is not None:
                self._engine.dispose()
                self._engine = None


def get_engine(request: Request) -> Engine:
    try:
        return cast(DatabaseResources, request.app.state.database).engine()
    except (ValueError, SQLAlchemyError):
        raise DatabaseUnavailable from None


def database_healthy(request: Request) -> bool:
    try:
        return check_database(get_engine(request))
    except DatabaseUnavailable:
        return False


def get_session(
    request: Request,
    identity: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> Iterator[Session]:
    # Authentication is resolved before engine construction, even if DB is absent.
    engine = get_engine(request)
    with session_scope(build_session_factory(engine)) as session:
        yield session
