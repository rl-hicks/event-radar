"""Explicit migration entrypoint, separate from API and personal CLI startup."""

from sqlalchemy import create_engine, pool

from alembic import context
from event_radar.db.config import database_url
from event_radar.db.models import Base

# Importing models registers metadata without database I/O.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        compare_server_default=True,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    supplied = context.config.attributes.get("connection")
    if supplied is not None:
        context.configure(
            connection=supplied,
            target_metadata=target_metadata,
            compare_server_default=True,
            transaction_per_migration=False,
        )
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_server_default=True,
                transaction_per_migration=False,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
