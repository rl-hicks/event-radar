"""Schema metadata seam for future models and Alembic."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base; WP1 intentionally defines no tables."""
