"""Token cost arithmetic and the currency ladder behind every displayed price.

These two functions produce the euro figure the user reads on their usage
page and the one stored on every message. A defect here is silent by nature:
nothing raises, nothing looks wrong, the number is simply not the truth.

Both are covered together on purpose. `calculate_token_cost` and
`calculate_token_cost_at_date` are near-identical twins — same per-million
scaling, same cached-token rule, same live-rate → DB-rate → give-up-and-report-
USD ladder — differing only in which pricing lookup they call and in their
return shape. Twins drift; the differential class at the end pins them to the
same euro figure for the same inputs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.llm.pricing_service import AsyncPricingService, ModelPrice

pytestmark = pytest.mark.unit

USD_TO_EUR = Decimal("0.93")


def _price(**overrides: Any) -> ModelPrice:
    """Pricing for a token-billed model, $1/M in and $3/M out."""
    base: dict[str, Any] = {
        "model_name": "gpt-4.1-mini",
        "input_price": Decimal("1.00"),
        "cached_input_price": Decimal("0.25"),
        "output_price": Decimal("3.00"),
        "pricing_unit": "per_1m_tokens",
        "effective_from": datetime(2026, 1, 1, tzinfo=UTC),
    }
    base.update(overrides)
    return ModelPrice(**base)


def _service(price: ModelPrice | None) -> AsyncPricingService:
    """A service whose pricing lookups are stubbed; no database involved."""
    service = AsyncPricingService(db=MagicMock())
    service.get_active_model_price = AsyncMock(return_value=price)  # type: ignore[method-assign]
    service.get_model_price_at_date = AsyncMock(return_value=price)  # type: ignore[method-assign]
    service.get_active_currency_rate = AsyncMock(return_value=USD_TO_EUR)  # type: ignore[method-assign]
    return service


def _currency_api(rate: Decimal | None) -> Any:
    """Patch the live currency API with a fixed answer."""
    api = MagicMock()
    api.get_rate = AsyncMock(return_value=rate)
    return patch("src.infrastructure.external.currency_api.CurrencyRateService", return_value=api)


@pytest.fixture(autouse=True)
def euro_reporting(monkeypatch: pytest.MonkeyPatch) -> None:
    """Report in EUR — the configuration every shipped .env actually sets.

    The CODE default is USD (``DEFAULT_CURRENCY``), while `.env.example`,
    `.env.prod.example` and the local `.env` all set `DEFAULT_CURRENCY=EUR`.
    Leaving the test on the code default would exercise the branch nobody runs
    and leave the whole conversion ladder — live rate, DB fallback, give-up —
    uncovered. One test below pins the USD configuration explicitly.
    """
    from src.core.config import settings

    monkeypatch.setattr(settings, "default_currency", "EUR", raising=False)


class TestPricingUnavailable:
    """No price must never mean an invented price."""

    async def test_unknown_model_costs_zero_rather_than_raising(self) -> None:
        service = _service(None)

        with _currency_api(USD_TO_EUR):
            assert await service.calculate_token_cost("mystery", 1000, 500, 0) == (0.0, 0.0)
            assert (
                await service.calculate_token_cost_at_date(
                    "mystery", 1000, 500, 0, datetime.now(UTC)
                )
                == 0.0
            )

    @pytest.mark.parametrize("unit", ["per_audio_minute", "per_audio_hour"])
    async def test_an_audio_billed_model_is_not_charged_per_token(self, unit: str) -> None:
        """Billing an audio model per token would invent a cost out of nothing.

        Audio pricing goes through the audio helper; the token path must
        recognise the unit and decline rather than multiply a per-minute price
        by a token count.
        """
        service = _service(_price(pricing_unit=unit))

        with _currency_api(USD_TO_EUR):
            assert await service.calculate_token_cost("whisper", 100_000, 0, 0) == (0.0, 0.0)
            assert (
                await service.calculate_token_cost_at_date(
                    "whisper", 100_000, 0, 0, datetime.now(UTC)
                )
                == 0.0
            )


class TestArithmetic:
    """Prices are per MILLION tokens."""

    async def test_scaling_is_per_million(self) -> None:
        service = _service(_price())

        with _currency_api(USD_TO_EUR):
            usd, eur = await service.calculate_token_cost("gpt-4.1-mini", 1_000_000, 0, 0)

        assert usd == pytest.approx(1.00)
        assert eur == pytest.approx(1.00 * float(USD_TO_EUR))

    async def test_input_output_and_cached_are_summed_at_their_own_rates(self) -> None:
        service = _service(_price())

        with _currency_api(USD_TO_EUR):
            usd, _ = await service.calculate_token_cost(
                "gpt-4.1-mini",
                input_tokens=1_000_000,
                output_tokens=1_000_000,
                cached_tokens=1_000_000,
            )

        # 1.00 (in) + 3.00 (out) + 0.25 (cached)
        assert usd == pytest.approx(4.25)

    async def test_zero_usage_costs_zero(self) -> None:
        service = _service(_price())

        with _currency_api(USD_TO_EUR):
            assert await service.calculate_token_cost("gpt-4.1-mini", 0, 0, 0) == (0.0, 0.0)

    async def test_a_model_without_cached_pricing_ignores_cached_tokens(self) -> None:
        """Characterization, and the reason it is acceptable.

        When `cached_input_price` is None the cached tokens contribute nothing.
        That is only correct because providers which do not price cache reads
        separately report them INSIDE `input_tokens`; charging them again would
        double-bill. Pinned here so that a provider adapter which starts
        reporting cached tokens separately, without a cached price, fails this
        test instead of silently under-billing.
        """
        service = _service(_price(cached_input_price=None))

        with _currency_api(USD_TO_EUR):
            usd, _ = await service.calculate_token_cost("gpt-4.1-mini", 0, 0, 1_000_000)

        assert usd == 0.0

    async def test_cached_price_is_ignored_when_no_cached_token_was_used(self) -> None:
        service = _service(_price())

        with _currency_api(USD_TO_EUR):
            usd, _ = await service.calculate_token_cost("gpt-4.1-mini", 1_000_000, 0, 0)

        assert usd == pytest.approx(1.00)


class TestCurrencyLadder:
    """Live rate → last synced rate → report USD and say so."""

    async def test_the_live_rate_is_preferred(self) -> None:
        service = _service(_price())

        with _currency_api(Decimal("0.80")):
            _, eur = await service.calculate_token_cost("gpt-4.1-mini", 1_000_000, 0, 0)

        assert eur == pytest.approx(0.80)
        service.get_active_currency_rate.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_the_stored_rate_takes_over_when_the_api_answers_nothing(self) -> None:
        service = _service(_price())

        with _currency_api(None):
            _, eur = await service.calculate_token_cost("gpt-4.1-mini", 1_000_000, 0, 0)

        assert eur == pytest.approx(float(USD_TO_EUR))
        service.get_active_currency_rate.assert_awaited_once()  # type: ignore[attr-defined]

    async def test_without_any_rate_the_usd_figure_is_returned_unconverted(self) -> None:
        """Never silently pass a USD number off as euros… but do not lose it either."""
        service = _service(_price())
        service.get_active_currency_rate = AsyncMock(  # type: ignore[method-assign]
            side_effect=ValueError("no rate in DB")
        )

        with _currency_api(None):
            usd, eur = await service.calculate_token_cost("gpt-4.1-mini", 1_000_000, 0, 0)
            at_date = await service.calculate_token_cost_at_date(
                "gpt-4.1-mini", 1_000_000, 0, 0, datetime.now(UTC)
            )

        assert usd == pytest.approx(1.00)
        assert eur == usd
        assert at_date == pytest.approx(1.00)

    async def test_no_conversion_when_the_configured_currency_is_already_usd(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        service = _service(_price())

        from src.core.config import settings

        monkeypatch.setattr(settings, "default_currency", "USD", raising=False)

        with _currency_api(Decimal("0.10")) as api_class:
            usd, eur = await service.calculate_token_cost("gpt-4.1-mini", 1_000_000, 0, 0)

        assert usd == eur == pytest.approx(1.00)
        api_class.assert_not_called()


class TestTheTwinsAgree:
    """The historical and the current calculator must produce one number."""

    @pytest.mark.parametrize(
        "input_tokens,output_tokens,cached_tokens",
        [
            (0, 0, 0),
            (1_000, 500, 0),
            (1_000_000, 1_000_000, 1_000_000),
            (37, 11, 5),
        ],
    )
    async def test_same_inputs_yield_the_same_euro_figure(
        self, input_tokens: int, output_tokens: int, cached_tokens: int
    ) -> None:
        service = _service(_price())

        with _currency_api(USD_TO_EUR):
            _, eur_now = await service.calculate_token_cost(
                "gpt-4.1-mini", input_tokens, output_tokens, cached_tokens
            )
            eur_at_date = await service.calculate_token_cost_at_date(
                "gpt-4.1-mini", input_tokens, output_tokens, cached_tokens, datetime.now(UTC)
            )

        assert eur_at_date == pytest.approx(eur_now)

    async def test_both_normalize_the_model_name_before_looking_it_up(self) -> None:
        """A dated model id must hit the same pricing row as its base name."""
        service = _service(_price())

        with _currency_api(USD_TO_EUR):
            await service.calculate_token_cost("o1-mini-2024-09-12", 1_000, 0, 0)
            await service.calculate_token_cost_at_date(
                "o1-mini-2024-09-12", 1_000, 0, 0, datetime.now(UTC)
            )

        looked_up_now = service.get_active_model_price.await_args.args[0]  # type: ignore[attr-defined]
        looked_up_at_date = service.get_model_price_at_date.await_args.args[0]  # type: ignore[attr-defined]
        assert looked_up_now == looked_up_at_date
        assert "2024-09-12" not in looked_up_now


class TestTimeSlotTariffs:
    """UTC time-slot pricing (ADR-223): the slot's prices replace the base
    prices while its window is active; outside every window the base
    columns apply. Both twins must resolve the slot from the SAME single
    implementation, or peak/off-peak costs drift between live tracking
    and historical recompute."""

    PEAK_SLOTS = [
        {
            "start_utc": "01:00",
            "end_utc": "04:00",
            "input_unit_price": 2.0,
            "cached_input_unit_price": 0.5,
            "output_unit_price": 6.0,
        },
        {
            "start_utc": "06:00",
            "end_utc": "10:00",
            "input_unit_price": 2.0,
            "cached_input_unit_price": 0.5,
            "output_unit_price": 6.0,
        },
    ]
    PEAK_AT = datetime(2026, 8, 17, 2, 30, tzinfo=UTC)
    OFF_PEAK_AT = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)

    def _windowed_service(self) -> AsyncPricingService:
        return _service(_price(time_slots=self.PEAK_SLOTS))

    async def test_peak_window_applies_the_slot_prices(self) -> None:
        service = self._windowed_service()

        with _currency_api(USD_TO_EUR):
            usd, _ = await service.calculate_token_cost(
                "gpt-4.1-mini", 1_000_000, 1_000_000, 1_000_000, at=self.PEAK_AT
            )

        # 2.0 (in) + 6.0 (out) + 0.5 (cached)
        assert usd == pytest.approx(8.5)

    async def test_off_peak_falls_back_to_the_base_prices(self) -> None:
        service = self._windowed_service()

        with _currency_api(USD_TO_EUR):
            usd, _ = await service.calculate_token_cost(
                "gpt-4.1-mini", 1_000_000, 1_000_000, 1_000_000, at=self.OFF_PEAK_AT
            )

        # 1.00 (in) + 3.00 (out) + 0.25 (cached) — the flat tariff
        assert usd == pytest.approx(4.25)

    async def test_the_historical_twin_uses_the_timestamp_it_is_given(self) -> None:
        """A message sent during a peak window must keep its peak cost when
        recomputed later — the slot is resolved at ``at_date``, never at
        wall-clock now."""
        service = self._windowed_service()

        with _currency_api(USD_TO_EUR):
            eur_peak = await service.calculate_token_cost_at_date(
                "gpt-4.1-mini", 1_000_000, 0, 0, self.PEAK_AT
            )
            eur_off = await service.calculate_token_cost_at_date(
                "gpt-4.1-mini", 1_000_000, 0, 0, self.OFF_PEAK_AT
            )

        assert eur_peak == pytest.approx(2.0 * float(USD_TO_EUR))
        assert eur_off == pytest.approx(1.0 * float(USD_TO_EUR))

    async def test_the_twins_agree_inside_and_outside_windows(self) -> None:
        service = self._windowed_service()

        with _currency_api(USD_TO_EUR):
            for at in (self.PEAK_AT, self.OFF_PEAK_AT):
                _, eur_now = await service.calculate_token_cost(
                    "gpt-4.1-mini", 37_000, 11_000, 5_000, at=at
                )
                eur_at_date = await service.calculate_token_cost_at_date(
                    "gpt-4.1-mini", 37_000, 11_000, 5_000, at
                )
                assert eur_at_date == pytest.approx(eur_now)

    async def test_a_slot_without_cached_price_charges_nothing_for_cache(self) -> None:
        slots = [{**self.PEAK_SLOTS[0], "cached_input_unit_price": None}]
        service = _service(_price(time_slots=slots))

        with _currency_api(USD_TO_EUR):
            usd, _ = await service.calculate_token_cost(
                "gpt-4.1-mini", 0, 0, 1_000_000, at=self.PEAK_AT
            )

        assert usd == 0.0

    async def test_flat_pricing_is_unchanged_when_no_slots_exist(self) -> None:
        service = _service(_price())

        with _currency_api(USD_TO_EUR):
            usd_peak, _ = await service.calculate_token_cost(
                "gpt-4.1-mini", 1_000_000, 0, 0, at=self.PEAK_AT
            )
            usd_off, _ = await service.calculate_token_cost(
                "gpt-4.1-mini", 1_000_000, 0, 0, at=self.OFF_PEAK_AT
            )

        assert usd_peak == usd_off == pytest.approx(1.00)


class TestCaching:
    """The service caches so the cost path does not hit the database per call."""

    @staticmethod
    def _rate_row(value: str = "0.93") -> Any:
        row = MagicMock()
        row.rate = Decimal(value)
        return row

    def _service_with_rate(self, row: Any) -> AsyncPricingService:
        db = MagicMock()
        scalars = MagicMock()
        scalars.first = MagicMock(return_value=row)
        db.scalars = AsyncMock(return_value=scalars)
        return AsyncPricingService(db=db)

    async def test_a_currency_rate_is_read_from_the_database_only_once(self) -> None:
        """Cost is computed on EVERY LLM call; a per-call SELECT is the defect.

        `_get_currency_rate_cached` used to stamp the cache timestamp and then
        query unconditionally, never storing the value — `_currency_rate_cache`
        was written by nobody and only ever cleared. The name, the docstring
        ("manual caching is used instead of @lru_cache") and the invalidation
        machinery all described a cache that did not exist.
        """
        service = self._service_with_rate(self._rate_row())

        first = await service.get_active_currency_rate("USD", "EUR")
        second = await service.get_active_currency_rate("USD", "EUR")

        assert first == second == Decimal("0.93")
        assert (
            service.db.scalars.await_count == 1
        ), "the rate was re-queried — the cache stores nothing"

    async def test_an_expired_rate_is_re_queried(self) -> None:
        service = self._service_with_rate(self._rate_row())
        service.cache_ttl = 0  # every entry is stale on the next read

        await service.get_active_currency_rate("USD", "EUR")
        await service.get_active_currency_rate("USD", "EUR")

        assert service.db.scalars.await_count == 2

    async def test_distinct_currency_pairs_do_not_share_an_entry(self) -> None:
        service = self._service_with_rate(self._rate_row())

        await service.get_active_currency_rate("USD", "EUR")
        await service.get_active_currency_rate("GBP", "EUR")

        assert service.db.scalars.await_count == 2

    async def test_a_missing_rate_raises_and_caches_nothing(self) -> None:
        service = self._service_with_rate(None)

        with pytest.raises(ValueError, match="Currency rate not found"):
            await service.get_active_currency_rate("USD", "EUR")
        with pytest.raises(ValueError):
            await service.get_active_currency_rate("USD", "EUR")

        assert service.db.scalars.await_count == 2

    async def test_invalidate_all_caches_forces_a_fresh_read(self) -> None:
        service = self._service_with_rate(self._rate_row())

        await service.get_active_currency_rate("USD", "EUR")
        service.invalidate_all_caches()
        await service.get_active_currency_rate("USD", "EUR")

        assert service.db.scalars.await_count == 2
