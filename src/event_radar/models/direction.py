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
    created_at: datetime
    update_id: int
