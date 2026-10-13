"""Private development linking; never registered as a product HTTP operation."""

from sqlalchemy.orm import Session

from event_radar.auth.config import auth_config
from event_radar.auth.verifier import get_verifier
from event_radar.db.delivery import DeliveryDenied, challenge


def request_operator_challenge(
    session: Session, access_token: str, *, approved: bool = False
) -> str:
    # Operator execution permission is separate from ordinary account authentication.
    # No account-ID or destination argument exists; the verified JWT selects ownership.
    if not approved:
        raise DeliveryDenied
    uid, _ = get_verifier(auth_config()).verify(access_token)
    return challenge(session, uid)
