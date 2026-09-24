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
from types import SimpleNamespace

import pytest

from src.domains.llm.models import LLMProviderEnum, PricingUnitEnum
from src.infrastructure.cache import pricing_cache
from src.infrastructure.cache.pricing_cache import (
    CachedModelPrice,
    PricingCacheData,
    build_price_index,
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

#: Claude Opus 5 on platform.claude.com/docs/en/about-claude/pricing (2026-09-23):
#: base input $5, « 5m cache writes » $6.25 per million tokens.
CLAUDE_INPUT_PRICE = 5.0
CLAUDE_5M_WRITE_PRICE = 6.25

PEAK_AT = datetime(2026, 8, 17, 2, 30, tzinfo=UTC)
OFF_PEAK_AT = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


def _tariff_row(
    name: str, provider: LLMProviderEnum, *, input_price: float = 1.0
) -> SimpleNamespace:
    """An active tariff row as ``build_price_index`` reads it (model joined)."""
    return SimpleNamespace(
        model=SimpleNamespace(model_name=name, provider=provider),
        input_unit_price=input_price,
        output_unit_price=2,
        cached_input_unit_price=0,
        pricing_unit=PricingUnitEnum.per_1m_tokens,
        time_slots=None,
        audio_input_unit_price=None,
        audio_output_unit_price=None,
    )


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
            "claude-opus-5": CachedModelPrice(
                input_unit_price=CLAUDE_INPUT_PRICE,
                output_unit_price=25.0,
                cached_input_unit_price=0.5,
                pricing_unit="per_1m_tokens",
                cache_write_multiplier=1.25,
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
# Prompt-cache writes (ADR-306)
# ============================================================================


class TestCacheWriteSurcharge:
    """A written token is a prompt token, owed the write rate on top."""

    def test_a_written_token_costs_the_published_write_price(self) -> None:
        """The prompt count INCLUDES the writes (``UsageTokens``): the whole
        million is written, so the call costs exactly the « 5m cache writes »
        column of the vendor's table."""
        usd, eur = get_cached_cost_usd_eur("claude-opus-5", MILLION, 0, cache_write_tokens=MILLION)
        assert usd == pytest.approx(CLAUDE_5M_WRITE_PRICE)
        assert eur == pytest.approx(CLAUDE_5M_WRITE_PRICE * USD_EUR)

    def test_only_the_written_part_pays_the_surcharge(self) -> None:
        usd, _ = get_cached_cost_usd_eur(
            "claude-opus-5", 2 * MILLION, 0, cache_write_tokens=MILLION
        )
        assert usd == pytest.approx(CLAUDE_INPUT_PRICE + CLAUDE_5M_WRITE_PRICE)

    def test_no_write_no_surcharge(self) -> None:
        usd, _ = get_cached_cost_usd_eur("claude-opus-5", MILLION, 0)
        assert usd == pytest.approx(CLAUDE_INPUT_PRICE)

    def test_a_tariff_without_a_write_surcharge_bills_a_write_as_input(self) -> None:
        """The count reaches every tariff; only a declared multiplier charges it."""
        usd, _ = get_cached_cost_usd_eur("no-cache-model", MILLION, 0, cache_write_tokens=MILLION)
        assert usd == pytest.approx(INPUT_PRICE)

    def test_the_surcharge_follows_the_input_price_of_a_time_slot(self) -> None:
        cache = pricing_cache._local_cache
        assert cache is not None
        cache.models["deepseek-v4-flash"].cache_write_multiplier = 1.25
        usd, _ = get_cached_cost_usd_eur(
            "deepseek-v4-flash", MILLION, 0, cache_write_tokens=MILLION, at=PEAK_AT
        )
        assert usd == pytest.approx(INPUT_PRICE * 2 * 1.25)

    def test_the_multiplier_is_the_providers_rule_set_when_the_index_is_built(self) -> None:
        """Claude and OpenAI tariffs carry 1.25; nobody else's does (pricing pages, 2026-09-23).

        OpenAI bills a write on GPT-5.6 and GPT-6 alone, and those are the only
        models that report one: on a repeated prefix, eleven earlier models
        answered ``cache_write_tokens: 0`` and gpt-4o-mini no such field (measured
        the same day), so the provider's rule prices every write it can meet.
        """
        index = build_price_index(
            [
                _tariff_row("claude-opus-5", LLMProviderEnum.anthropic),
                _tariff_row("gpt-6-luna", LLMProviderEnum.openai),
                _tariff_row("qwen3.5-plus", LLMProviderEnum.qwen),
                _tariff_row("gemini-3.8-flash", LLMProviderEnum.gemini),
            ]
        )
        assert index["claude-opus-5"].cache_write_multiplier == 1.25
        assert index["gpt-6-luna"].cache_write_multiplier == 1.25
        # DashScope's explicit cache writes at 125 % (ADR-309); a Qwen model with
        # an implicit cache reports no write, so the provider's rule prices only
        # the writes the explicit markers produce.
        assert index["qwen3.5-plus"].cache_write_multiplier == 1.25
        assert index["gemini-3.8-flash"].cache_write_multiplier == 1.0

    def test_a_gpt6_write_costs_the_published_cache_write_price(self) -> None:
        """gpt-6-luna: input $0.10, « cache writes » $0.125 per million (pricing page)."""
        index = build_price_index(
            [_tariff_row("gpt-6-luna", LLMProviderEnum.openai, input_price=0.10)]
        )
        cache = pricing_cache._local_cache
        assert cache is not None
        cache.models["gpt-6-luna"] = index["gpt-6-luna"]
        usd, _ = get_cached_cost_usd_eur("gpt-6-luna", MILLION, 0, cache_write_tokens=MILLION)
        assert usd == pytest.approx(0.125)

    def test_a_blob_written_before_the_multiplier_still_loads(self) -> None:
        """Rolling deploy: an older worker's blob has no such key."""
        blob = json.dumps(
            {
                "models": {
                    "claude-opus-5": {
                        "input_unit_price": 5.0,
                        "output_unit_price": 25.0,
                        "cached_input_unit_price": 0.5,
                        "pricing_unit": "per_1m_tokens",
                    }
                },
                "usd_eur_rate": USD_EUR,
                "last_refresh_ts": 0.0,
            }
        )
        restored = PricingCacheData.from_json(blob)
        assert restored.models["claude-opus-5"].cache_write_multiplier == 1.0

    def test_the_multiplier_survives_the_redis_round_trip(self) -> None:
        cache = pricing_cache._local_cache
        assert cache is not None
        restored = PricingCacheData.from_json(cache.to_json())
        assert restored.models["claude-opus-5"].cache_write_multiplier == 1.25

    def test_the_currency_wrapper_carries_the_writes(self) -> None:
        from src.infrastructure.cache.pricing_cache import get_cached_cost

        with_write = get_cached_cost("claude-opus-5", MILLION, 0, cache_write_tokens=MILLION)
        without = get_cached_cost("claude-opus-5", MILLION, 0)
        assert with_write == pytest.approx(without * 1.25)


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
