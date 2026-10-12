"""Private context persistence; callers must supply the verified account UUID."""

import hashlib
import json
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from event_radar.db.models import AppUser, UserContextRevision
from event_radar.db.users import get_or_create_user
from event_radar.models.product_context import ContextRevision, ProductUserContext


class ContextConflict(Exception):
    """No private content or revision identity in error messages."""


class ContextCorrupt(Exception):
    pass


def content_hash(context: ProductUserContext) -> str:
    payload = context.model_dump(mode="json")
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def read_context(session: Session, authenticated_id: UUID) -> ContextRevision | None:
    row = session.scalar(
        select(UserContextRevision)
        .where(UserContextRevision.user_id == authenticated_id)
        .order_by(UserContextRevision.revision.desc())
        .limit(1)
    )
    if row is None:
        return None
    try:
        context = ProductUserContext.model_validate(row.context_payload)
        if (
            content_hash(context) != row.content_hash
            or context.schema_version != row.schema_version
        ):
            raise ValueError
        return ContextRevision(
            revision_id=row.id,
            revision=row.revision,
            created_at=row.created_at,
            content_hash=row.content_hash,
            context=context,
        )
    except Exception:
        raise ContextCorrupt from None


def write_context(
    session: Session,
    authenticated_id: UUID,
    context: ProductUserContext,
    *,
    expected_revision_id: UUID | None,
) -> ContextRevision:
    # Validate again at the service boundary; model_construct/model_copy cannot bypass it.
    validated = ProductUserContext.model_validate(context.model_dump(mode="json", warnings=False))
    get_or_create_user(session, authenticated_id)
    # Account row exists even before initial context: serializes initial creation and updates.
    session.execute(
        select(AppUser.id).where(AppUser.id == authenticated_id).with_for_update()
    ).one()
    current = read_context(session, authenticated_id)
    if (current.revision_id if current else None) != expected_revision_id:
        raise ContextConflict
    row = UserContextRevision(
        id=uuid4(),
        user_id=authenticated_id,
        revision=current.revision + 1 if current else 1,
        schema_version=validated.schema_version,
        content_hash=content_hash(validated),
        context_payload=validated.model_dump(mode="json"),
    )
    session.add(row)
    session.flush()
    return ContextRevision(
        revision_id=row.id,
        revision=row.revision,
        created_at=row.created_at,
        content_hash=row.content_hash,
        context=validated,
    )
