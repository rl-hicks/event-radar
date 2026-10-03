"""Foundation identity persistence, called only with a backend-authenticated UUID."""

from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from event_radar.db.models import AppUser


def get_or_create_user(session: Session, authenticated_id: UUID) -> AppUser:
    user = session.get(AppUser, authenticated_id)
    if user is None:
        session.execute(
            insert(AppUser)
            .values(id=authenticated_id)
            .on_conflict_do_nothing(index_elements=[AppUser.id])
        )
        # Under PostgreSQL READ COMMITTED this subsequent statement sees a row
        # committed by a concurrent creator after ON CONFLICT finishes waiting.
        user = session.get(AppUser, authenticated_id)
    if user is None:
        raise RuntimeError("Identity row unavailable after insert")
    return user
