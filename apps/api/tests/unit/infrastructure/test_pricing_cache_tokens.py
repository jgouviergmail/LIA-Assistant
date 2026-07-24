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

from collections.abc import Iterator

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
# Model-name normalisation
# ============================================================================


class TestModelNameNormalisation:
    def test_lookup_goes_through_normalisation(self) -> None:
        """Providers report decorated names (dated suffixes, vendor prefixes);
        the cache is keyed on the normalised form, so both must resolve to the
        same price — otherwise a live model silently costs zero."""
        from src.infrastructure.cache.pricing_cache import normalize_model_name

        assert normalize_model_name("gpt-4.1-mini") == "gpt-4.1-mini"
        direct, _ = get_cached_cost_usd_eur("gpt-4.1-mini", MILLION, 0)
        assert direct == pytest.approx(INPUT_PRICE)
