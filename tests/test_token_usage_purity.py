from types import SimpleNamespace

from event_radar.models.token_usage import ModelTokenPricing, parse_token_usage


def test_pricing_can_be_supplied_without_settings_import() -> None:
    rates = SimpleNamespace(
        input_usd_per_million=2.0,
        cached_input_usd_per_million=0.1,
        output_usd_per_million=10.0,
    )
    pricing = ModelTokenPricing.from_mapping({"shared-model": rates}, "shared-model")
    assert pricing == ModelTokenPricing(2.0, 0.1, 10.0)
    usage = SimpleNamespace(
        input_tokens=100,
        input_tokens_details=SimpleNamespace(cached_tokens=40),
        output_tokens=20,
        total_tokens=120,
    )
    assert parse_token_usage(usage, pricing).estimated_model_cost_usd == 0.000324
