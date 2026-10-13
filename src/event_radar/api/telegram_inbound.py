"""Optional webhook factory; absent from normal startup until explicitly injected."""

import hmac
import json
import re
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.orm import Session

from event_radar.api.dependencies import get_engine
from event_radar.db.delivery import DeliveryDenied, accept_private_update


def webhook_router(secret: str) -> APIRouter:
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", secret):
        raise ValueError("A separately generated webhook secret is required.")
    router = APIRouter()

    @router.post("/api/integrations/telegram/webhook")
    async def receive(request: Request) -> dict[str, bool]:
        headers = request.headers.getlist("x-telegram-bot-api-secret-token")
        if len(headers) != 1 or not hmac.compare_digest(headers[0].encode(), secret.encode()):
            raise HTTPException(status_code=403)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 16384:
                raise HTTPException(status_code=413)
        try:
            update = json.loads(raw)
            message = update["message"]
            sender, chat = message["from"], message["chat"]
            parts = message["text"].split()
            if (
                type(update["update_id"]) is not int
                or len(parts) != 2
                or parts[0] != "/start"
                or sender["is_bot"] is not False
                or "forward_origin" in message
                or "sender_chat" in message
                or type(message["date"]) is not int
                or not 0 <= datetime.now(UTC).timestamp() - message["date"] <= 600
            ):
                raise ValueError
            with Session(get_engine(request)) as session, session.begin():
                accept_private_update(
                    session,
                    parts[1],
                    sender_id=sender["id"],
                    chat_id=chat["id"],
                    chat_type=chat["type"],
                    sender_is_bot=sender["is_bot"],
                )
        except (ValueError, TypeError, KeyError, DeliveryDenied):
            # Acknowledge unusable/replayed updates; do not induce uncontrolled provider retries.
            return {"accepted": False}
        return {"accepted": True}

    return router
