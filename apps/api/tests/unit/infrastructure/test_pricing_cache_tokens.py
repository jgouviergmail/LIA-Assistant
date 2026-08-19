"""Unit tests for the TOKEN-billed branch of the pricing cache.

``get_cached_cost_usd_eur`` is the synchronous source of truth for what every
LLM call costs — it feeds token tracking, the per-message cost shown to the
user, and the budget/usage limits. It is deliberately fail-soft (returns
``(0.0, 0.0)`` rather than raising) so a pricing gap never breaks a
conversation, which is precisely why a regression here is invisible: the calls
keep working and the cost silently reads zero, or double.

The audio branch has its own file; this one pins the token arithmetic, the
three fail-soft exits, and the bucket contract shared with ``TokenExtractor``
(input tokens EXCLUDE cached ones — they are priced additively here).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from src.infrastructure.cache import pricing_cache
from src.infrastructure.cache.pricing_cache import (
    CachedModelPrice,
    PricingCacheData,
    get_cached_cost_usd_eur,
)

pytestmark = pytest.mark.unit

INPUT_PRICE = 0.40  # USD per 1M input tokens
OUTPUT_PRICE = 1.60
CACHED_PRICE = 0.10
USD_EUR = 0.9
MILLION = 1_000_000

# DeepSeek-shaped windowed tariff: base = off-peak, peak costs double
# during 01:00-04:00 and 06:00-10:00 UTC (verified 2026-08-17).
PEAK_SLOTS = [
    {
        "start_utc": "01:00",
        "end_utc": "04:00",
        "input_unit_price": INPUT_PRICE * 2,
        "cached_input_unit_price": CACHED_PRICE * 2,
        "output_unit_price": OUTPUT_PRICE * 2,
    },
    {
        "start_utc": "06:00",
        "end_utc": "10:00",
        "input_unit_price": INPUT_PRICE * 2,
        "cached_input_unit_price": CACHED_PRICE * 2,
        "output_unit_price": OUTPUT_PRICE * 2,
    },
]

PEAK_AT = datetime(2026, 8, 17, 2, 30, tzinfo=UTC)
OFF_PEAK_AT = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _populate_local_cache() -> Iterator[None]:
    """Seed ``_local_cache`` with deterministic prices, then restore."""
    cache_before = pricing_cache._local_cache
    pricing_cache._local_cache = PricingCacheData(
        models={
            "gpt-4.1-mini": CachedModelPrice(
                input_unit_price=INPUT_PRICE,
                output_unit_price=OUTPUT_PRICE,
                cached_input_unit_price=CACHED_PRICE,
                pricing_unit="per_1m_tokens",
            ),
            "no-cache-model": CachedModelPrice(
                input_unit_price=INPUT_PRICE,
                output_unit_price=OUTPUT_PRICE,
                cached_input_unit_price=0.0,
                pricing_unit="per_1m_tokens",
            ),
            "scribe_v2": CachedModelPrice(
                input_unit_price=0.22,
                output_unit_price=0.0,
                cached_input_unit_price=0.0,
                pricing_unit="per_audio_hour",
            ),
            "deepseek-v4-flash": CachedModelPrice(
                input_unit_price=INPUT_PRICE,
                output_unit_price=OUTPUT_PRICE,
                cached_input_unit_price=CACHED_PRICE,
                pricing_unit="per_1m_tokens",
                time_slots=PEAK_SLOTS,
            ),
        },
        usd_eur_rate=USD_EUR,
        last_refresh_ts=0.0,
    )
    yield
    pricing_cache._local_cache = cache_before


# ============================================================================
# Arithmetic
# ============================================================================


class TestTokenCostArithmetic:
    def test_input_and_output_are_priced_separately(self) -> None:
        usd, eur = get_cached_cost_usd_eur("gpt-4.1-mini", MILLION, MILLION)
        assert usd == pytest.approx(INPUT_PRICE + OUTPUT_PRICE)
        assert eur == pytest.approx((INPUT_PRICE + OUTPUT_PRICE) * USD_EUR)

    def test_prices_are_per_million_tokens(self) -> None:
        usd, _ = get_cached_cost_usd_eur("gpt-4.1-mini", 1000, 0)
        assert usd == pytest.approx(INPUT_PRICE * 1000 / MILLION)

    def test_cached_tokens_use_the_discounted_rate(self) -> None:
        usd, _ = get_cached_cost_usd_eur("gpt-4.1-mini", 0, 0, cached_tokens=MILLION)
        assert usd == pytest.approx(CACHED_PRICE)

    def test_the_three_buckets_are_additive(self) -> None:
        """This additivity is exactly why ``TokenExtractor`` must hand over
        input tokens with the cache reads already removed."""
        usd, _ = get_cached_cost_usd_eur("gpt-4.1-mini", MILLION, MILLION, MILLION)
        assert usd == pytest.approx(INPUT_PRICE + OUTPUT_PRICE + CACHED_PRICE)

    def test_caching_is_cheaper_than_plain_input(self) -> None:
        """The whole point of prompt caching — pin it so a price inversion in
        the seed data surfaces as a failure, not as a bigger invoice."""
        full, _ = get_cached_cost_usd_eur("gpt-4.1-mini", MILLION, 0)
        cached, _ = get_cached_cost_usd_eur("gpt-4.1-mini", 0, 0, cached_tokens=MILLION)
        assert cached < full

    def test_a_model_without_cache_pricing_charges_nothing_for_cache(self) -> None:
        usd, _ = get_cached_cost_usd_eur("no-cache-model", 0, 0, cached_tokens=MILLION)
        assert usd == pytest.approx(0.0)

    def test_zero_tokens_cost_zero(self) -> None:
        assert get_cached_cost_usd_eur("gpt-4.1-mini", 0, 0) == (0.0, 0.0)

    def test_eur_conversion_applies_the_cached_rate(self) -> None:
        usd, eur = get_cached_cost_usd_eur("gpt-4.1-mini", 500_000, 250_000)
        assert eur == pytest.approx(usd * USD_EUR)


# ============================================================================
# Fail-soft exits (never raise, never invent a price)
# ============================================================================


class TestFailSoftExits:
    def test_unknown_model_costs_zero(self) -> None:
        """A model missing from the cache must not be guessed at."""
        assert get_cached_cost_usd_eur("model-we-never-priced", MILLION, MILLION) == (0.0, 0.0)

    def test_audio_priced_model_is_refused_by_the_token_branch(self) -> None:
        """Audio models are billed per minute/hour — pricing them per token
        would silently produce a nonsense amount."""
        assert get_cached_cost_usd_eur("scribe_v2", MILLION, MILLION) == (0.0, 0.0)

    def test_uninitialised_cache_costs_zero(self) -> None:
        pricing_cache._local_cache = None
        assert get_cached_cost_usd_eur("gpt-4.1-mini", MILLION, MILLION) == (0.0, 0.0)


# ============================================================================
# UTC time-slot tariffs (ADR-223)
# ============================================================================


class TestTimeSlotPricing:
    def test_peak_window_applies_the_slot_prices(self) -> None:
        usd, eur = get_cached_cost_usd_eur("deepseek-v4-flash", MILLION, MILLION, at=PEAK_AT)
        assert usd == pytest.approx((INPUT_PRICE + OUTPUT_PRICE) * 2)
        assert eur == pytest.approx(usd * USD_EUR)

    def test_outside_every_window_the_base_prices_apply(self) -> None:
        usd, _ = get_cached_cost_usd_eur("deepseek-v4-flash", MILLION, MILLION, at=OFF_PEAK_AT)
        assert usd == pytest.approx(INPUT_PRICE + OUTPUT_PRICE)

    def test_cached_tokens_use_the_slot_cached_rate_during_a_window(self) -> None:
        usd, _ = get_cached_cost_usd_eur(
            "deepseek-v4-flash", 0, 0, cached_tokens=MILLION, at=PEAK_AT
        )
        assert usd == pytest.approx(CACHED_PRICE * 2)

    def test_a_slot_without_cached_price_charges_nothing_for_cache(self) -> None:
        """Mirror of the base-price rule: providers without separate cache
        billing report cache reads inside input_tokens — charging them here
        would double-bill during the window only."""
        cache = pricing_cache._local_cache
        assert cache is not None
        slots = [{**PEAK_SLOTS[0], "cached_input_unit_price": None}]
        cache.models["deepseek-v4-flash"] = CachedModelPrice(
            input_unit_price=INPUT_PRICE,
            output_unit_price=OUTPUT_PRICE,
            cached_input_unit_price=CACHED_PRICE,
            pricing_unit="per_1m_tokens",
            time_slots=slots,
        )
        usd, _ = get_cached_cost_usd_eur(
            "deepseek-v4-flash", 0, 0, cached_tokens=MILLION, at=PEAK_AT
        )
        assert usd == pytest.approx(0.0)

    def test_flat_priced_models_ignore_the_at_parameter(self) -> None:
        peak, _ = get_cached_cost_usd_eur("gpt-4.1-mini", MILLION, MILLION, at=PEAK_AT)
        off, _ = get_cached_cost_usd_eur("gpt-4.1-mini", MILLION, MILLION, at=OFF_PEAK_AT)
        assert peak == off == pytest.approx(INPUT_PRICE + OUTPUT_PRICE)

    def test_default_at_is_now_utc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Callers on the hot path pass no ``at`` — the call instant is the
        billing instant, matching what the provider invoices."""

        class _FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz: object = None) -> datetime:  # type: ignore[override]
                return PEAK_AT

        monkeypatch.setattr(pricing_cache, "datetime", _FrozenDatetime)
        usd, _ = get_cached_cost_usd_eur("deepseek-v4-flash", MILLION, 0)
        assert usd == pytest.approx(INPUT_PRICE * 2)

    def test_old_redis_blob_without_time_slots_still_deserializes(self) -> None:
        """Rolling-deploy safety: a blob written by the previous release has
        no ``time_slots`` key and must load as flat pricing, not crash."""
        old_blob = json.dumps(
            {
                "models": {
                    "gpt-4.1-mini": {
                        "input_unit_price": INPUT_PRICE,
                        "output_unit_price": OUTPUT_PRICE,
                        "cached_input_unit_price": CACHED_PRICE,
                        "pricing_unit": "per_1m_tokens",
                    }
                },
                "usd_eur_rate": USD_EUR,
                "last_refresh_ts": 0.0,
            }
        )
        data = PricingCacheData.from_json(old_blob)
        assert data.models["gpt-4.1-mini"].time_slots is None

    def test_redis_round_trip_preserves_time_slots(self) -> None:
        """Serialization-pair rule: slots must survive Redis verbatim, or a
        worker restart silently reverts every model to flat pricing."""
        cache = pricing_cache._local_cache
        assert cache is not None
        restored = PricingCacheData.from_json(cache.to_json())
        assert restored.models["deepseek-v4-flash"].time_slots == PEAK_SLOTS
        assert restored.models["gpt-4.1-mini"].time_slots is None


# ============================================================================
# Model-name normalisation
# ============================================================================


class TestModelNameNormalisation:
    """A decorated name must still be billed — and never at zero.

    The cache is keyed on the catalogue's **exact** name; normalisation is the
    fallback applied at lookup time (``resolve_priced_name``), so a dated model
    inherits its base model's price while a dated model that owns an explicit
    tariff keeps its own (production defect, ``gpt-4o-2024-05-13``).
    """

    def test_undecorated_name_resolves_to_its_own_price(self) -> None:
        direct, _ = get_cached_cost_usd_eur("gpt-4.1-mini", MILLION, 0)
        assert direct == pytest.approx(INPUT_PRICE)

    def test_dated_name_falls_back_to_the_base_model_price(self) -> None:
        """Otherwise a live model would silently cost zero."""
        decorated, _ = get_cached_cost_usd_eur("gpt-4.1-mini-2025-04-14", MILLION, 0)
        assert decorated == pytest.approx(INPUT_PRICE)

    def test_unknown_model_costs_zero_rather_than_guessing(self) -> None:
        unknown, _ = get_cached_cost_usd_eur("no-such-model", MILLION, 0)
        assert unknown == 0.0
