from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from event_radar.config import settings


class ProductDatabaseConfigurationError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    if settings.database_url is None:
        raise ProductDatabaseConfigurationError("DATABASE_URL is not configured.")
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
    )


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


def check_database(session: Session) -> None:
    session.execute(text("SELECT 1"))
