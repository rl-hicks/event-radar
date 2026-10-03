from uuid import UUID

from sqlalchemy.orm import Session

from event_radar.db.models import AppUser


def get_or_create_app_user(session: Session, user_id: UUID) -> AppUser:
    existing = session.get(AppUser, user_id)
    if existing is not None:
        return existing

    user = AppUser(id=user_id)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
