from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class DirectionType(StrEnum):
    TEMPORARY = "temporary"
    PERMANENT = "permanent"


class Direction(BaseModel):
    type: DirectionType
    text: str
    telegram_user_id: int
    # Optional defaults preserve compatibility with directions stored before
    # private-chat transport metadata was captured.
    telegram_chat_id: int | None = None
    telegram_chat_type: str | None = None
    created_at: datetime
    update_id: int
