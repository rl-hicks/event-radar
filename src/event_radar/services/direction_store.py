import json
from pathlib import Path

from event_radar.models.direction import Direction, DirectionType

STATE_DIR = Path("state")
OFFSET_PATH = STATE_DIR / "telegram_offset.json"
PERMANENT_PATH = STATE_DIR / "permanent_directions.json"
TEMPORARY_PATH = STATE_DIR / "temporary_directions.json"


def load_offset() -> int:
    payload = json.loads(OFFSET_PATH.read_text())
    return int(payload["next_offset"])


def save_offset(next_offset: int) -> None:
    OFFSET_PATH.write_text(
        json.dumps(
            {"next_offset": next_offset},
            indent=2,
        )
        + "\n"
    )


def save_direction(direction: Direction) -> None:
    if direction.type is DirectionType.PERMANENT:
        path = PERMANENT_PATH
    else:
        path = TEMPORARY_PATH

    existing = json.loads(path.read_text())
    existing.append(direction.model_dump(mode="json"))

    path.write_text(json.dumps(existing, indent=2) + "\n")


def load_permanent_directions() -> list[Direction]:
    payload = json.loads(PERMANENT_PATH.read_text())
    return [Direction.model_validate(item) for item in payload]


def load_temporary_directions() -> list[Direction]:
    payload = json.loads(TEMPORARY_PATH.read_text())
    return [Direction.model_validate(item) for item in payload]


def clear_temporary_directions() -> None:
    TEMPORARY_PATH.write_text("[]\n")
