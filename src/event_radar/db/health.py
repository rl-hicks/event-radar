"""Internal connectivity primitive; no HTTP route or import-time I/O."""

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError


def check_database(engine: Engine) -> bool:
    """Check an explicitly supplied engine; build_engine supplies timeout bounds."""
    try:
        with engine.connect() as connection:
            return bool(connection.scalar(text("SELECT 1")) == 1)
    except SQLAlchemyError:
        return False
