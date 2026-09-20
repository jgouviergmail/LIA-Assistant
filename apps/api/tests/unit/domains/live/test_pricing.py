"""A live model is offered and started only when the tariff table declares it (ADR-300 wave 3).

The rates the start publishes feed the banner's indicative meter — counted
in the browser on the person's own key, recorded nowhere.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.domains.live.errors import LiveRefusedError
from src.domains.live.pricing import is_priced, rates_for, split_priced
from src.domains.live.schemas import LiveModel, LiveModelCapabilitiesResponse
from src.infrastructure.cache import pricing_cache
from src.infrastructure.cache.pricing_cache import CachedModelPrice, PricingCacheData
from tests.unit.domains.live.conftest import GEMINI_LIVE_PRICE, USD_EUR_RATE
from tests.unit.domains.live.test_service import (
    CMODULE,
    MODULE,
    USER,
    _chosen,
    _connector,
    _fake_provider,
    _service,
)

pytestmark = pytest.mark.unit


def _model(name: str, provider: str = "gemini") -> LiveModel:
    return LiveModel(
        provider=provider,
        name=name,
        thinking_levels=[],
        capabilities=LiveModelCapabilitiesResponse(
            **dict.fromkeys(LiveModelCapabilitiesResponse.model_fields, True)
        ),
    )


# -- the seam ----------------------------------------------------------------


def test_rates_are_the_tariffs_with_the_cached_exchange_rate() -> None:
    rates = rates_for("gemini-3.8-live")
    assert rates is not None
    assert rates.pricing_unit == "per_1m_tokens"
    assert (rates.input_unit_price, rates.output_unit_price) == (0.75, 4.5)
    assert (rates.audio_input_unit_price, rates.audio_output_unit_price) == (3.0, 12.0)
    assert rates.usd_eur_rate == USD_EUR_RATE


def test_a_minute_billed_model_publishes_no_audio_pair() -> None:
    rates = rates_for("gpt-live-1")
    assert rates is not None
    assert rates.pricing_unit == "per_audio_minute"
    assert rates.audio_input_unit_price is None and rates.audio_output_unit_price is None


def test_an_undeclared_model_has_no_rates_and_is_not_priced() -> None:
    assert rates_for("gemini-99-live-unknown") is None
    assert is_priced("gemini-99-live-unknown") is False


def test_a_dated_name_inherits_its_base_tariff() -> None:
    # The pricing chain's own rule (resolve_priced_name): exact name first, then normalised.
    assert is_priced("gemini-3.8-live-2026-09-19") is True


def test_a_cold_cache_prices_nothing() -> None:
    before = pricing_cache._local_cache
    pricing_cache._local_cache = None
    try:
        assert rates_for("gemini-3.8-live") is None
        assert split_priced(["gemini-3.8-live"]) == ([], ["gemini-3.8-live"])
    finally:
        pricing_cache._local_cache = before


def test_split_keeps_the_input_order_on_both_sides() -> None:
    assert split_priced(["x-unknown", "gpt-live-1", "gemini-3.8-live", "y-unknown"]) == (
        ["gpt-live-1", "gemini-3.8-live"],
        ["x-unknown", "y-unknown"],
    )


# -- the listing --------------------------------------------------------------


async def test_the_listing_offers_the_declared_models_and_names_the_rest() -> None:
    service, _, _ = _service(_connector())
    provider = _fake_provider()
    provider.list_models = AsyncMock(
        return_value=[
            _model("gemini-3.8-live"),
            _model("gemini-99-live-unknown"),
            _model("gemini-3.8-live-extended-thinking"),
        ]
    )
    with patch(f"{CMODULE}.PROVIDERS", {"gemini_live": provider}):
        listing = await service.connectors.list_models(USER, language="fr")
    assert [m.name for m in listing.models] == [
        "gemini-3.8-live",
        "gemini-3.8-live-extended-thinking",
    ]
    assert listing.unpriced == ["gemini-99-live-unknown"]


async def test_the_discovery_before_the_connector_exists_applies_the_same_rule() -> None:
    service, _, _ = _service(None)
    provider = _fake_provider()
    provider.list_models = AsyncMock(
        return_value=[_model("gemini-99-live-unknown"), _model("gemini-3.8-live")]
    )
    with (
        patch(f"{CMODULE}.ConnectorService") as connectors,
        patch(f"{CMODULE}.provider_by_id", return_value=provider),
    ):
        connectors.return_value.validate_api_key = AsyncMock(return_value=(True, "ok"))
        listing = await service.connectors.discover_models(
            "AIza-test-key", provider_id="gemini", language="fr"
        )
    assert [m.name for m in listing.models] == ["gemini-3.8-live"]
    assert listing.unpriced == ["gemini-99-live-unknown"]


async def test_a_vendor_billed_providers_models_are_offered_whatever_the_tariff_table_holds() -> (
    None
):
    # Owner rule 2026-09-20: the agents API runs on the person's own key and the
    # platform prices NOTHING of it — an ElevenLabs agent is offered with no
    # tariff row of ours, never named as « unpriced », and the vendor's own bill
    # is what the person sees at the end.
    service, _, _ = _service(None)
    provider = _fake_provider()
    provider.provider_id = "elevenlabs"
    provider.billing = "vendor"
    provider.default_model = ""
    provider.list_models = AsyncMock(
        return_value=[
            _model("agent_0123456789abcdef", provider="elevenlabs"),
            _model("agent_fedcba9876543210", provider="elevenlabs"),
        ]
    )
    with (
        patch(f"{CMODULE}.ConnectorService") as connectors,
        patch(f"{CMODULE}.provider_by_id", return_value=provider),
    ):
        connectors.return_value.validate_api_key = AsyncMock(return_value=(True, "ok"))
        listing = await service.connectors.discover_models(
            "sk_test", provider_id="elevenlabs", language="fr"
        )
    assert [m.name for m in listing.models] == [
        "agent_0123456789abcdef",
        "agent_fedcba9876543210",
    ]
    assert listing.unpriced == []
    assert "elevenlabs-agents" not in (
        pricing_cache._local_cache.models if pricing_cache._local_cache else {}
    )


# -- the write path and the start ---------------------------------------------


async def test_choosing_an_undeclared_model_is_refused_before_the_probe() -> None:
    service, _, _ = _service(_connector())
    provider = _fake_provider()
    with patch(f"{CMODULE}.PROVIDERS", {"gemini_live": provider}):
        with pytest.raises(LiveRefusedError) as raised:
            await service.connectors.update_connector_settings(
                USER, "gemini", _chosen(model="gemini-99-live-unknown"), language="fr"
            )
    assert raised.value.code == "model_unpriced"
    assert "gemini-99-live-unknown" in raised.value.detail["message"]
    provider.probe.assert_not_awaited()


async def test_start_publishes_the_models_rates() -> None:
    service, _, _ = _service(_connector())
    provider = _fake_provider()
    with patch(f"{MODULE}.PROVIDERS", {"gemini_live": provider}):
        response = await service.start(
            USER, language="fr", timezone="Europe/Paris", display_name="Alex"
        )
    assert response.rates.audio_output_unit_price == GEMINI_LIVE_PRICE.audio_output_unit_price
    assert response.rates.usd_eur_rate == USD_EUR_RATE


async def test_start_on_a_connector_whose_model_lost_its_tariff_is_refused_409() -> None:
    # The tariff was retired after the connector was configured: the settings
    # would no longer offer the model, and the start says the same word.
    service, store, _ = _service(_connector(model="gemini-99-live-unknown"))
    provider = _fake_provider()
    with patch(f"{MODULE}.PROVIDERS", {"gemini_live": provider}):
        with pytest.raises(LiveRefusedError) as raised:
            await service.start(USER, language="fr", timezone="Europe/Paris", display_name="Alex")
    assert raised.value.code == "model_unpriced"
    assert raised.value.status_code == 409
    store.claim.assert_not_awaited()
    provider.mint.assert_not_awaited()


async def test_a_token_billed_tariff_without_its_audio_pair_does_not_declare_a_live_model() -> None:
    # The text rates alone would leave every turn's cost unavailable and a
    # ceiling unenforceable: not declared for the live mode, refused at the
    # start with the same word the settings would not offer it under.
    assert pricing_cache._local_cache is not None
    pricing_cache._local_cache = PricingCacheData(
        models={
            **pricing_cache._local_cache.models,
            "gemini-3.8-live": CachedModelPrice(
                input_unit_price=0.75,
                output_unit_price=4.5,
                cached_input_unit_price=0.0,
                pricing_unit="per_1m_tokens",
            ),
        },
        usd_eur_rate=USD_EUR_RATE,
        last_refresh_ts=0.0,
    )
    assert is_priced("gemini-3.8-live") is False
    assert is_priced("gpt-live-1") is True  # a minute-billed tariff needs no pair
    service, store, _ = _service(_connector())
    provider = _fake_provider()
    with patch(f"{MODULE}.PROVIDERS", {"gemini_live": provider}):
        with pytest.raises(LiveRefusedError) as raised:
            await service.start(USER, language="fr", timezone="Europe/Paris", display_name="Alex")
    assert raised.value.code == "model_unpriced"
    store.claim.assert_not_awaited()


async def test_a_vendor_billed_session_starts_with_no_rates() -> None:
    """The platform prices nothing of it: the meter shows the clock, the vendor bills."""
    # The connector's type stays the fake's (gemini_live): only the provider's
    # billing decides, never its name.
    service, _, _ = _service(_connector(model="agent_0123456789abcdef", voice="agent"))
    provider = _fake_provider()
    provider.billing = "vendor"
    with patch(f"{MODULE}.PROVIDERS", {"gemini_live": provider}):
        started = await service.start(USER, language="fr", timezone="UTC", display_name="Alex")
    assert started.rates is None
