"""Unit tests for deterministic resolution of a model's active tariff.

Two defects motivate this module, both measured on real data (2026-08-18):

- **Non-determinism**: several rows could carry ``is_active`` for the same
  model and the read paths selected without ``ORDER BY``, so the cache and
  ``AsyncPricingService`` disagreed on the very same database — measured at a
  factor 4 on ``gemini-2.5-flash-preview-tts`` and at a *unit* change on
  ``scribe_v2``.
- **Name shadowing**: the cache index is keyed by the raw ``model_name`` while
  lookups normalise the name first, so a dated model was billed under its base
  model. Measured in production: ``gpt-4o-2024-05-13`` owns a 5.00/15.00 tariff
  but was billed 2.50/10.00 (``gpt-4o``'s).

The pure helpers are tested here rather than the SQL ordering, on purpose: the
partial unique index added by migration ``6e7f8a9b0c1d`` makes duplicate active
rows impossible to create, so a behavioural test of the ordering would need to
defeat the very constraint that protects production. The index itself is
covered by ``test_active_uniqueness_migration.py``.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.llm_utils import resolve_priced_name
from src.domains.llm.pricing_service import AsyncPricingService
from src.infrastructure.cache.pricing_cache import build_price_index
from tests.helpers.llm_helpers import create_llm_pricing_async


def _pricing_row(model_name: str, input_price: str, unit: str = "per_1m_tokens") -> Any:
    """Build a minimal stand-in for an LLMModelPricing row with its model loaded."""
    return SimpleNamespace(
        input_unit_price=Decimal(input_price),
        output_unit_price=Decimal("1.0"),
        cached_input_unit_price=None,
        pricing_unit=SimpleNamespace(value=unit),
        time_slots=None,
        model=SimpleNamespace(model_name=model_name),
    )


class TestResolvePricedName:
    """The single lookup rule shared by every read path."""

    def test_prefers_the_exact_name_over_the_normalised_one(self) -> None:
        index = {"gpt-4o": 1, "gpt-4o-2024-05-13": 2}
        assert resolve_priced_name("gpt-4o-2024-05-13", index.__contains__) == ("gpt-4o-2024-05-13")

    def test_falls_back_to_the_normalised_name(self) -> None:
        index = {"gpt-4o": 1}
        assert resolve_priced_name("gpt-4o-2024-05-13", index.__contains__) == "gpt-4o"

    def test_returns_none_when_neither_name_is_priced(self) -> None:
        index = {"gpt-4o": 1}
        assert resolve_priced_name("claude-3-5-haiku-20241022", index.__contains__) is None

    def test_undated_name_resolves_to_itself(self) -> None:
        index = {"gpt-5.2": 1}
        assert resolve_priced_name("gpt-5.2", index.__contains__) == "gpt-5.2"

    def test_does_not_invent_a_name_for_an_unknown_model(self) -> None:
        assert resolve_priced_name("totally-unknown", {}.__contains__) is None


class TestBuildPriceIndex:
    """The cache index keeps the first row of a deterministic ordering."""

    def test_indexes_every_model_by_its_raw_name(self) -> None:
        index = build_price_index([_pricing_row("gpt-5.2", "1.0"), _pricing_row("o1-mini", "2.0")])
        assert set(index) == {"gpt-5.2", "o1-mini"}
        assert index["gpt-5.2"].input_unit_price == 1.0

    def test_first_row_wins_so_a_legacy_duplicate_cannot_shadow_the_current_tariff(
        self,
    ) -> None:
        # Rows arrive ordered by (effective_from DESC, id DESC): the most recent
        # one comes first and must survive. A database predating the unique
        # index can still hold duplicates.
        rows = [_pricing_row("dup", "3.0"), _pricing_row("dup", "9.0")]
        assert build_price_index(rows)["dup"].input_unit_price == 3.0

    def test_preserves_the_billing_unit(self) -> None:
        index = build_price_index([_pricing_row("scribe_v2", "0.22", unit="per_audio_hour")])
        assert index["scribe_v2"].pricing_unit == "per_audio_hour"

    def test_absent_cached_price_becomes_zero(self) -> None:
        index = build_price_index([_pricing_row("gpt-5.2", "1.0")])
        assert index["gpt-5.2"].cached_input_unit_price == 0.0

    def test_empty_input_yields_an_empty_index(self) -> None:
        assert build_price_index([]) == {}


class TestAsyncPricingServiceResolution:
    """The database read path applies the same rule as the cache."""

    async def test_dated_model_is_billed_its_own_tariff_when_it_owns_one(
        self,
        async_session: AsyncSession,
    ) -> None:
        await create_llm_pricing_async(
            async_session,
            model_name="gpt-4o",
            input_price=Decimal("2.5"),
            output_price=Decimal("10"),
        )
        await create_llm_pricing_async(
            async_session,
            model_name="gpt-4o-2024-05-13",
            input_price=Decimal("5"),
            output_price=Decimal("15"),
        )
        service = AsyncPricingService(async_session)

        price = await service.get_active_model_price("gpt-4o-2024-05-13")

        assert price is not None
        assert price.input_price == Decimal("5")
        assert price.output_price == Decimal("15")

    async def test_dated_model_inherits_the_base_tariff_when_it_owns_none(
        self,
        async_session: AsyncSession,
    ) -> None:
        await create_llm_pricing_async(
            async_session,
            model_name="claude-3-5-haiku",
            input_price=Decimal("0.8"),
            output_price=Decimal("4"),
        )
        service = AsyncPricingService(async_session)

        price = await service.get_active_model_price("claude-3-5-haiku-20241022")

        assert price is not None
        assert price.input_price == Decimal("0.8")

    async def test_unknown_model_resolves_to_nothing(
        self,
        async_session: AsyncSession,
    ) -> None:
        service = AsyncPricingService(async_session)

        assert await service.get_active_model_price("no-such-model-anywhere") is None
