"""Unit tests for the audio-billed branch of the pricing cache.

Covers ``get_cached_cost_audio_usd_eur`` against the three pricing units and
asserts the guard on ``get_cached_cost_usd_eur`` (the token-based variant
must short-circuit when called against an audio-priced model).
"""

from __future__ import annotations

import pytest

from src.infrastructure.cache import pricing_cache
from src.infrastructure.cache.pricing_cache import (
    CachedModelPrice,
    PricingCacheData,
    get_cached_cost_audio_usd_eur,
    get_cached_cost_usd_eur,
)


@pytest.fixture(autouse=True)
def _populate_local_cache():
    """Seed ``_local_cache`` with deterministic prices for tests."""
    cache_before = pricing_cache._local_cache
    pricing_cache._local_cache = PricingCacheData(
        models={
            # Token-priced model.
            "gpt-4.1-mini": CachedModelPrice(
                input_unit_price=0.40,
                output_unit_price=1.60,
                cached_input_unit_price=0.10,
                pricing_unit="per_1m_tokens",
            ),
            # Audio-priced model: $0.22 per audio hour (ElevenLabs Scribe).
            "scribe_v2": CachedModelPrice(
                input_unit_price=0.22,
                output_unit_price=0.0,
                cached_input_unit_price=0.0,
                pricing_unit="per_audio_hour",
            ),
            # Audio-priced model: $0.10 per audio minute (hypothetical).
            "audiominute": CachedModelPrice(
                input_unit_price=0.10,
                output_unit_price=0.0,
                cached_input_unit_price=0.0,
                pricing_unit="per_audio_minute",
            ),
        },
        usd_eur_rate=0.9,
        last_refresh_ts=0.0,
    )
    yield
    pricing_cache._local_cache = cache_before


def test_audio_hour_cost_one_full_hour():
    """1 hour of audio at $0.22/h → $0.22 USD, ~€0.198 EUR."""
    cost_usd, cost_eur = get_cached_cost_audio_usd_eur("scribe_v2", 3600)
    assert cost_usd == pytest.approx(0.22, rel=1e-9)
    assert cost_eur == pytest.approx(0.22 * 0.9, rel=1e-9)


def test_audio_hour_cost_subsecond_precision():
    """100 ms of audio remains representable above the Decimal(10,6) floor."""
    cost_usd, _ = get_cached_cost_audio_usd_eur("scribe_v2", 0.1)
    expected_usd = (0.1 / 3600.0) * 0.22
    assert cost_usd == pytest.approx(expected_usd, rel=1e-9)
    # Sanity: still > 0 so the persistence layer attaches a real value.
    assert cost_usd > 0


def test_audio_hour_cost_typical_call():
    """30 s of audio @ $0.22/h → $0.001833 USD."""
    cost_usd, _ = get_cached_cost_audio_usd_eur("scribe_v2", 30.0)
    assert cost_usd == pytest.approx(30.0 / 3600.0 * 0.22, rel=1e-9)


def test_audio_minute_cost():
    """30 s of audio @ $0.10/min → $0.05 USD."""
    cost_usd, cost_eur = get_cached_cost_audio_usd_eur("audiominute", 30.0)
    assert cost_usd == pytest.approx(30.0 / 60.0 * 0.10, rel=1e-9)
    assert cost_eur == pytest.approx(cost_usd * 0.9, rel=1e-9)


def test_audio_cost_zero_duration_returns_zero():
    assert get_cached_cost_audio_usd_eur("scribe_v2", 0) == (0.0, 0.0)


def test_audio_cost_negative_duration_returns_zero():
    assert get_cached_cost_audio_usd_eur("scribe_v2", -1.0) == (0.0, 0.0)


def test_audio_cost_unknown_model_returns_zero():
    assert get_cached_cost_audio_usd_eur("unknown-model", 60.0) == (0.0, 0.0)


def test_audio_cost_called_on_token_priced_model_returns_zero():
    """Wrong-pricing-unit guard: refuses to apply audio formula on tokens."""
    assert get_cached_cost_audio_usd_eur("gpt-4.1-mini", 60.0) == (0.0, 0.0)


def test_token_cost_called_on_audio_priced_model_returns_zero():
    """Symmetric guard: token-cost helper refuses audio-priced models."""
    assert get_cached_cost_usd_eur("scribe_v2", 1000, 500) == (0.0, 0.0)


def test_audio_cost_no_cache_returns_zero():
    """Sane fallback when the cache has not been initialised yet."""
    pricing_cache._local_cache = None
    assert get_cached_cost_audio_usd_eur("scribe_v2", 60.0) == (0.0, 0.0)
