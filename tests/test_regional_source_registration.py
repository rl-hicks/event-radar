from event_radar.collectors.regional_sources import (
    default_sonoma_source_registry,
    happening_sonoma_adapter,
    sonoma_county_tourism_adapter,
)


def test_initial_sonoma_sources_register_through_shared_adapter_contract() -> None:
    tourism = sonoma_county_tourism_adapter(user_agent="EventRadar/Test")
    happening = happening_sonoma_adapter(user_agent="EventRadar/Test")

    assert tourism.descriptor.source_id == "sonoma-county-tourism"
    assert tourism.descriptor.mechanism == "html"
    assert happening.descriptor.source_id == "happening-sonoma-county"
    assert happening.descriptor.mechanism == "api"

    registry = default_sonoma_source_registry(user_agent="EventRadar/Test")
    assert tuple(
        registration.adapter.descriptor.source_id for registration in registry.registrations
    ) == (
        "sonoma-county-tourism",
        "happening-sonoma-county",
        "curated-sonoma-hikes",
    )
