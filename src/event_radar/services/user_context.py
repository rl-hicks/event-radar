import json
from pathlib import Path

from pydantic import ValidationError

from event_radar.models.user_context import UserContext


class UserContextError(RuntimeError):
    """Raised when the required private user policy cannot be loaded."""


class UserContextRepository:
    def __init__(self, path: Path = Path("config/user_context.json")) -> None:
        self._path = path

    def load(self) -> UserContext:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise UserContextError(f"Required user context was not found at {self._path}.") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise UserContextError(f"Could not read user context at {self._path}.") from exc

        try:
            return UserContext.model_validate(payload)
        except ValidationError as exc:
            raise UserContextError(f"User context at {self._path} is invalid: {exc}") from exc
