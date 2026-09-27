from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class CurationConfig:
    event_description_max_characters: int = 1_200
    maximum_hike_candidates: int = 10
    maximum_web_discoveries: int = 12
    maximum_event_options: int = 22
    maximum_hike_options: int = 6
    reasoning_effort: Literal["low", "medium", "high"] = "medium"


DEFAULT_CURATION_CONFIG = CurationConfig()
