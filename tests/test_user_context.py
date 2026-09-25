import json
import subprocess
from pathlib import Path

import pytest

from event_radar.models.user_context import (
    AvailabilityStatus,
    PreferenceStrength,
    SoloFriction,
)
from event_radar.services.user_context import UserContextError, UserContextRepository
from tests.curation_helpers import example_user_context


def test_example_profile_validates() -> None:
    context = UserContextRepository(Path("config/user_context.example.json")).load()

    assert context.profile_id == "example-profile"
    assert context.output_preferences.absolute_maximum == 18


def test_valid_user_context_loads_from_explicit_fixture(tmp_path: Path) -> None:
    context = example_user_context()
    path = tmp_path / "user-context.json"
    path.write_text(context.model_dump_json(), encoding="utf-8")

    loaded = UserContextRepository(path).load()

    assert loaded == context


@pytest.mark.parametrize("payload", ["not-json", json.dumps({"profile_id": "missing"})])
def test_invalid_user_context_fails_clearly(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(UserContextError, match="(?i)user context"):
        UserContextRepository(path).load()


def test_missing_user_context_does_not_fall_back_to_generic_profile(tmp_path: Path) -> None:
    with pytest.raises(UserContextError, match="Required user context"):
        UserContextRepository(tmp_path / "missing.json").load()


def test_real_user_context_path_is_gitignored() -> None:
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", "config/user_context.json"],
        check=False,
    )

    assert result.returncode == 0


def test_recurring_availability_models_open_time_and_soft_anchor() -> None:
    windows = {item.id: item for item in example_user_context().recurring_availability}

    friday = windows["friday-open"]
    climbing = windows["saturday-climbing"]
    saturday_open = windows["saturday-open"]
    sunday = windows["sunday-open"]

    assert friday.status is AvailabilityStatus.OPEN
    assert friday.start_time is None and friday.end_time is None
    assert climbing.status is AvailabilityStatus.SOFT_ANCHOR
    assert climbing.start_time is not None and climbing.start_time.hour == 8
    assert climbing.end_time is not None and climbing.end_time.hour == 12
    assert saturday_open.status is AvailabilityStatus.OPEN
    assert saturday_open.start_time is not None and saturday_open.start_time.hour == 12
    assert saturday_open.end_time is None
    assert sunday.status is AvailabilityStatus.OPEN
    assert sunday.start_time is None and sunday.end_time is None


def test_drive_cost_solo_and_category_policy_are_structured() -> None:
    context = example_user_context()

    assert context.drive_tolerance[-1].maximum_minutes is None
    assert context.cost_tolerance[-1].maximum_dollars is None
    assert context.solo_attendance["concerts"] is SoloFriction.MODERATE
    assert context.category_priors["workshops"].strength is PreferenceStrength.STRONG
