"""PostgreSQL session claim for standalone regional workers (no schema change).

Use a direct/session-pooled PostgreSQL connection, never transaction pooling.
The dedicated connection is retained across short committed transactions and
invalidated on exit, so a session lock cannot leak back into the engine pool.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256

from sqlalchemy import Connection, Engine, select, text
from sqlalchemy.orm import Session

from event_radar.db.models import RegionalResearchRun, RegionalUniverse
from event_radar.db.regional import fail_regional_research_run
from event_radar.models.regional import ResearchIdentity


@dataclass
class RegionalClaim:
    session: Session
    connection: Connection

    def check_connection(self) -> None:
        if self.connection.invalidated or self.connection.closed:
            raise RuntimeError("Regional claim connection was lost; retry requires a new claim.")

    def recover_abandoned(self, identity: ResearchIdentity) -> None:
        """Only a lock holder can declare previous running attempts abandoned."""
        runs = self.session.scalars(
            select(RegionalResearchRun)
            .join(RegionalUniverse, RegionalResearchRun.universe_id == RegionalUniverse.id)
            .where(
                RegionalUniverse.region_id == identity.region_id,
                RegionalUniverse.weekend_friday == identity.friday,
                RegionalUniverse.research_policy_version == identity.research_policy_version,
                RegionalResearchRun.status == "running",
            )
        ).all()
        for run in runs:
            fail_regional_research_run(self.session, run.id, failure_code="unavailable")


@contextmanager
def claim_regional_research(
    engine: Engine, identity: ResearchIdentity
) -> Iterator[RegionalClaim | None]:
    """Nonblocking same-key exclusion, including before the identity row exists.

    All shared worker invocations must use this claim. WP6's low-level write
    helpers remain transaction primitives, not competing worker entrypoints.
    A terminated process loses its session lock; its committed running row is
    recovered by the next claimant. A hash collision only reduces concurrency.
    """
    key = int.from_bytes(sha256(identity.key.encode()).digest()[:8], "big", signed=True)
    with engine.connect() as connection:
        try:
            acquired = connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
            connection.commit()
            if not acquired:
                yield None
                return
            with Session(bind=connection, expire_on_commit=False) as session:
                yield RegionalClaim(session, connection)
        finally:
            # Close the actual PostgreSQL session even on cancellation/DB failure.
            # Never silently reconnect and finalize work after losing ownership.
            connection.invalidate()
