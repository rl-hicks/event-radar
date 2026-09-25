import json
import subprocess
from pathlib import Path

import pytest

from event_radar.models.user_context import PreferenceStrength, SoloFriction
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


def test_saturday_climbing_is_a_soft_anchor() -> None:
    anchor = next(
        item for item in example_user_context().schedule_anchors if item.id == "saturday-climbing"
    )

    assert anchor.day_of_week == "saturday"
    assert anchor.strength == "soft"
    assert anchor.start_time is not None and anchor.start_time.hour == 8
    assert anchor.end_time is not None and anchor.end_time.hour == 12


def test_drive_cost_solo_and_category_policy_are_structured() -> None:
    context = example_user_context()

    assert context.drive_tolerance[-1].maximum_minutes is None
    assert context.cost_tolerance[-1].maximum_dollars is None
    assert context.solo_attendance["concerts"] is SoloFriction.MODERATE
    assert context.category_priors["workshops"].strength is PreferenceStrength.STRONG
