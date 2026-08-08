import json
from pathlib import Path

from pydantic import ValidationError

from event_radar.models.hike import HikeCatalog

DEFAULT_HIKE_CATALOG_PATH = Path("data/hikes.json")


class HikeCatalogError(RuntimeError):
    """Raised when the curated hike catalog cannot be loaded or validated."""


class HikeCatalogRepository:
    """Load and validate the static curated hike catalog."""

    def __init__(self, path: Path = DEFAULT_HIKE_CATALOG_PATH) -> None:
        self._path = path

    def load(self) -> HikeCatalog:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise HikeCatalogError(f"Could not read hike catalog at {self._path}.") from exc
        except json.JSONDecodeError as exc:
            raise HikeCatalogError(f"Hike catalog at {self._path} is invalid JSON.") from exc

        try:
            return HikeCatalog.model_validate(payload)
        except ValidationError as exc:
            raise HikeCatalogError(f"Hike catalog at {self._path} failed validation.") from exc
