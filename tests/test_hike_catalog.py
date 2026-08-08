import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from event_radar.models.hike import (
    CoordinatePrecision,
    Difficulty,
    DriveFriction,
    RouteType,
    ScenicValue,
    SoloFit,
    ThreeLevel,
    TimeOfDay,
)
from event_radar.services.hike_catalog import (
    DEFAULT_HIKE_CATALOG_PATH,
    HikeCatalogError,
    HikeCatalogRepository,
)


def _payload() -> dict[str, Any]:
    return json.loads(DEFAULT_HIKE_CATALOG_PATH.read_text(encoding="utf-8"))


def _write_payload(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "hikes.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_curated_catalog_loads_all_records_and_preserves_metadata() -> None:
    catalog = HikeCatalogRepository().load()

    assert len(catalog.hikes) == 35
    assert catalog.catalog_metadata.record_count == 35
    assert catalog.catalog_metadata.catalog_name == "Event Radar North Bay Hiking Catalog"
    assert catalog.catalog_metadata.schema_version == "1.0.0"
    assert catalog.catalog_metadata.catalog_version == "2026-08-07"
    assert catalog.catalog_metadata.baseline_location.latitude == 38.44047
    assert catalog.catalog_metadata.units.distance == "miles"


def test_catalog_records_preserve_schema_and_invariants() -> None:
    catalog = HikeCatalogRepository().load()

    assert len({hike.id for hike in catalog.hikes}) == 35
    assert all(-90 <= hike.latitude <= 90 for hike in catalog.hikes)
    assert all(-180 <= hike.longitude <= 180 for hike in catalog.hikes)
    assert all(hike.distance_miles > 0 for hike in catalog.hikes)
    assert all(hike.elevation_gain_ft >= 0 for hike in catalog.hikes)
    assert all(
        hike.estimated_duration_minutes.min <= hike.estimated_duration_minutes.max
        for hike in catalog.hikes
    )
    assert all(hike.trail_sequence for hike in catalog.hikes)
    assert all(hike.official_source_url.scheme in {"http", "https"} for hike in catalog.hikes)
    assert all(hike.dynamic_status_check_required is True for hike in catalog.hikes)
    assert all(37.8 <= hike.latitude <= 38.7 for hike in catalog.hikes)
    assert all(-123.4 <= hike.longitude <= -122.4 for hike in catalog.hikes)
    assert all(
        set(
            [
                *hike.preferred_months,
                *hike.acceptable_months,
                *hike.poor_months,
            ]
        )
        == set(range(1, 13))
        for hike in catalog.hikes
    )

    pygmy = next(hike for hike in catalog.hikes if hike.id == "salt-point-pygmy-forest-loop")
    approximate_ids = {
        hike.id
        for hike in catalog.hikes
        if hike.coordinate_precision is CoordinatePrecision.APPROXIMATE_TRAILHEAD
    }
    assert approximate_ids == {
        "salt-point-pygmy-forest-loop",
        "sugarloaf-pony-gate-canyon-loop",
    }
    assert pygmy.coordinate_precision is CoordinatePrecision.APPROXIMATE_TRAILHEAD
    assert pygmy.provenance.derived_fields
    assert pygmy.data_quality.uncertainties
    assert "3.1-mile" in pygmy.data_quality.uncertainties[0]


def test_catalog_controlled_vocabularies_match_application_types() -> None:
    vocabulary = HikeCatalogRepository().load().catalog_metadata.controlled_vocabularies

    assert set(vocabulary.difficulty) == set(Difficulty)
    assert set(vocabulary.route_type) == set(RouteType)
    assert set(vocabulary.three_level_scale) == set(ThreeLevel)
    assert set(vocabulary.solo_fit) == set(SoloFit)
    assert set(vocabulary.scenic_value) == set(ScenicValue)
    assert set(vocabulary.best_time_of_day) == set(TimeOfDay)
    assert set(vocabulary.drive_friction_from_santa_rosa) == set(DriveFriction)
    assert set(vocabulary.coordinate_precision) == set(CoordinatePrecision)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: payload["catalog_metadata"].update(record_count=34),
            "record_count",
        ),
        (
            lambda payload: payload["hikes"][1].update(id=payload["hikes"][0]["id"]),
            "IDs must be unique",
        ),
        (
            lambda payload: payload["hikes"][0].update(
                preferred_months=[1],
                acceptable_months=[],
                poor_months=[],
            ),
            "partition all 12 months",
        ),
        (
            lambda payload: payload["hikes"][0]["estimated_duration_minutes"].update(
                min=90,
                max=45,
            ),
            "Duration maximum",
        ),
        (
            lambda payload: payload["hikes"][0].update(trail_sequence=[]),
            "trail_sequence",
        ),
        (
            lambda payload: payload["hikes"][0].update(official_source_url="not a URL"),
            "official_source_url",
        ),
        (
            lambda payload: payload["hikes"][0].update(difficulty="extreme"),
            "difficulty",
        ),
    ],
)
def test_malformed_catalog_records_fail_cleanly(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    payload = _payload()
    mutate(payload)
    path = _write_payload(tmp_path, payload)

    with pytest.raises(HikeCatalogError) as error:
        HikeCatalogRepository(path).load()

    assert message in str(error.value.__cause__)


def test_invalid_json_fails_cleanly(tmp_path: Path) -> None:
    path = tmp_path / "hikes.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(HikeCatalogError, match="invalid JSON"):
        HikeCatalogRepository(path).load()
