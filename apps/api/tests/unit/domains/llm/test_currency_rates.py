"""Unit tests for the single implementation of currency-rate replacement.

Replacing an exchange rate carries an invariant that is easy to get subtly
wrong: **exactly one row stays active per currency pair**. It was implemented
twice — once in the admin route, once in the daily scheduler — and the admin
copy deactivated only ``.first()`` of the active rows, which is how three
active ``EUR->USD`` rows appeared in the development database.

The invariant now has one implementation, tested here, and the partial unique
index added by migration ``6e7f8a9b0c1d`` turns any regression into an
``IntegrityError`` instead of a silent duplicate.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal

import pytest
import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.llm import currency_rates
from src.domains.llm.currency_rates import replace_active_rate
from src.domains.llm.models import CurrencyExchangeRate
from tests.support.structlog_capture import fresh_module_logger


@pytest.fixture
def _fresh_logger() -> Iterator[None]:
    yield from fresh_module_logger(currency_rates)


async def _active_rows(db: AsyncSession, pair: tuple[str, str]) -> list[CurrencyExchangeRate]:
    stmt = select(CurrencyExchangeRate).where(
        CurrencyExchangeRate.from_currency == pair[0],
        CurrencyExchangeRate.to_currency == pair[1],
        CurrencyExchangeRate.is_active,
    )
    return list((await db.scalars(stmt)).all())


@pytest.mark.unit
class TestReplaceActiveRate:
    async def test_creates_the_first_rate_of_a_pair(self, async_session: AsyncSession) -> None:
        created = await replace_active_rate(
            async_session, from_currency="USD", to_currency="CHF", rate=Decimal("0.88")
        )
        await async_session.flush()

        assert created.is_active is True
        assert created.rate == Decimal("0.88")
        assert len(await _active_rows(async_session, ("USD", "CHF"))) == 1

    async def test_leaves_exactly_one_active_row_after_replacement(
        self, async_session: AsyncSession
    ) -> None:
        await replace_active_rate(
            async_session, from_currency="USD", to_currency="GBP", rate=Decimal("0.79")
        )
        await async_session.flush()

        await replace_active_rate(
            async_session, from_currency="USD", to_currency="GBP", rate=Decimal("0.80")
        )
        await async_session.flush()

        rows = await _active_rows(async_session, ("USD", "GBP"))
        assert len(rows) == 1
        assert rows[0].rate == Decimal("0.80")

    async def test_deactivates_every_pre_existing_active_row_not_only_the_first(
        self, async_session: AsyncSession
    ) -> None:
        # The legacy state PRE-dates `uq_currency_rate_active` (ADR-228), which
        # the schema now carries: drop it for the staging, restore it before the
        # assertion, so the invariant is back in force while the result is read.
        await async_session.execute(text("DROP INDEX IF EXISTS uq_currency_rate_active"))
        # Reproduce the legacy state: several rows already carry is_active.
        for value in ("1.01", "1.02", "1.03"):
            async_session.add(
                CurrencyExchangeRate(
                    from_currency="USD",
                    to_currency="SEK",
                    rate=Decimal(value),
                    is_active=True,
                )
            )
        await async_session.flush()
        assert len(await _active_rows(async_session, ("USD", "SEK"))) == 3

        await replace_active_rate(
            async_session, from_currency="USD", to_currency="SEK", rate=Decimal("1.10")
        )
        await async_session.flush()

        # Restoring the index here is the real oracle: it only succeeds if the
        # replacement genuinely left ONE active row for the pair.
        await async_session.execute(
            text(
                "CREATE UNIQUE INDEX uq_currency_rate_active "
                "ON currency_exchange_rates (from_currency, to_currency) WHERE is_active"
            )
        )

        rows = await _active_rows(async_session, ("USD", "SEK"))
        assert len(rows) == 1, "every legacy active row must be deactivated, not just the first"
        assert rows[0].rate == Decimal("1.10")

    async def test_history_is_preserved(self, async_session: AsyncSession) -> None:
        await replace_active_rate(
            async_session, from_currency="USD", to_currency="NOK", rate=Decimal("10.5")
        )
        await async_session.flush()
        await replace_active_rate(
            async_session, from_currency="USD", to_currency="NOK", rate=Decimal("10.9")
        )
        await async_session.flush()

        total = await async_session.scalar(
            select(func.count())
            .select_from(CurrencyExchangeRate)
            .where(
                CurrencyExchangeRate.from_currency == "USD",
                CurrencyExchangeRate.to_currency == "NOK",
            )
        )
        assert total == 2, "superseded rates stay in the table as history"

    async def test_currency_codes_are_upper_cased(self, async_session: AsyncSession) -> None:
        created = await replace_active_rate(
            async_session, from_currency="usd", to_currency="jpy", rate=Decimal("150")
        )
        await async_session.flush()

        assert (created.from_currency, created.to_currency) == ("USD", "JPY")

    async def test_other_pairs_are_untouched(self, async_session: AsyncSession) -> None:
        await replace_active_rate(
            async_session, from_currency="USD", to_currency="DKK", rate=Decimal("6.8")
        )
        await async_session.flush()

        await replace_active_rate(
            async_session, from_currency="USD", to_currency="PLN", rate=Decimal("4.0")
        )
        await async_session.flush()

        assert len(await _active_rows(async_session, ("USD", "DKK"))) == 1
        assert len(await _active_rows(async_session, ("USD", "PLN"))) == 1


@pytest.mark.unit
class TestReplacementIsReportedHonestly:
    """The log must describe what happened, not what usually happens.

    An operator reading "rate replaced" on a pair that never had one would go
    looking for a predecessor that does not exist.
    """

    async def test_a_first_rate_is_logged_as_a_creation(
        self, async_session: AsyncSession, _fresh_logger: None
    ) -> None:
        with structlog.testing.capture_logs() as logs:
            await replace_active_rate(
                async_session, from_currency="USD", to_currency="MXN", rate=Decimal("17")
            )
            await async_session.flush()

        events = [entry["event"] for entry in logs]
        assert "currency_rate_created" in events
        assert "currency_rate_replaced" not in events

    async def test_a_superseding_rate_is_logged_as_a_replacement(
        self, async_session: AsyncSession, _fresh_logger: None
    ) -> None:
        await replace_active_rate(
            async_session, from_currency="USD", to_currency="ZAR", rate=Decimal("18")
        )
        await async_session.flush()

        with structlog.testing.capture_logs() as logs:
            await replace_active_rate(
                async_session, from_currency="USD", to_currency="ZAR", rate=Decimal("19")
            )
            await async_session.flush()

        replacement = next(entry for entry in logs if entry["event"] == "currency_rate_replaced")
        assert replacement["retired_rows"] == 1
        assert replacement["previous_rate"] == 18.0
