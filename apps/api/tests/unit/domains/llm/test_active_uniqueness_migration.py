"""Tests for migration ``6e7f8a9b0c1d`` — one active tariff, one active rate.

The migration's SQL is imported from the revision module rather than copied, so
these tests exercise the statements that actually run in production.

Doctrine under test: **a migration never chooses between two prices.** Strictly
identical duplicates collapse without losing information; genuinely divergent
ones stop the migration. That rule is not academic — the intuitive "keep the
most recent row" heuristic was checked against the four real divergent cases in
the development database and is wrong in four of four, production holding the
*older* values in every one.
"""

from __future__ import annotations

import importlib.util
from collections.abc import AsyncGenerator
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.llm.models import (
    CurrencyExchangeRate,
    LLMModelPricing,
    PricingUnitEnum,
)
from tests.helpers.llm_helpers import ensure_llm_model_async

_REVISION = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "2026_08_18_1400-6e7f8a9b0c1d_unique_active_pricing_and_rate.py"
)


def _load_revision() -> Any:
    spec = importlib.util.spec_from_file_location("_rev_6e7f8a9b0c1d", _REVISION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


revision = _load_revision()


#: The invariants the migration installs. A test that stages the state the
#: migration is meant to repair must run without them — exactly as the real
#: upgrade does, which collapses BEFORE creating them.
_ACTIVE_INDEXES: tuple[str, ...] = (
    "uq_llm_model_pricing_active",
    "uq_currency_rate_active",
)


@pytest_asyncio.fixture
async def without_active_indexes(async_session: AsyncSession) -> AsyncGenerator[None]:
    """Run the test on the PRE-migration schema.

    Without this, staging two active rows raises `IntegrityError` before the
    collapse under test ever runs — the setup would fail for the very reason
    the migration exists.

    Nothing is restored on the way out, and that is deliberate twice over: the
    DROP lives inside the test's transaction, which the harness rolls back
    (PostgreSQL DDL is transactional), and `TestRefuseDivergentDuplicates`
    leaves divergent duplicates standing ON PURPOSE — re-creating a unique
    index over them could only fail, turning the behaviour under test into a
    teardown error.
    """
    for name in _ACTIVE_INDEXES:
        await async_session.execute(text(f"DROP INDEX IF EXISTS {name}"))
    await async_session.flush()
    yield


async def _add_pricing(
    db: AsyncSession,
    model_name: str,
    *,
    input_price: str,
    unit: PricingUnitEnum = PricingUnitEnum.per_1m_tokens,
) -> LLMModelPricing:
    """Insert an active pricing row directly, bypassing the service invariant."""
    model = await ensure_llm_model_async(db, model_name)
    row = LLMModelPricing(
        model_id=model.id,
        input_unit_price=Decimal(input_price),
        cached_input_unit_price=None,
        output_unit_price=Decimal("1"),
        pricing_unit=unit,
        is_active=True,
    )
    db.add(row)
    await db.flush()
    return row


@pytest.mark.unit
class TestCollapseIdenticalDuplicates:
    async def test_identical_active_rows_collapse_to_one(
        self, async_session: AsyncSession, without_active_indexes: None
    ) -> None:
        await _add_pricing(async_session, "collapse-me", input_price="2.0")
        await _add_pricing(async_session, "collapse-me", input_price="2.0")

        await async_session.execute(text(revision.COLLAPSE_IDENTICAL_PRICING_SQL))

        rows = await _active_pricing(async_session, "collapse-me")
        assert len(rows) == 1

    async def test_the_surviving_row_is_the_most_recent(
        self, async_session: AsyncSession, without_active_indexes: None
    ) -> None:
        older = await _add_pricing(async_session, "keep-recent", input_price="2.0")
        newer = await _add_pricing(async_session, "keep-recent", input_price="2.0")
        assert newer.effective_from >= older.effective_from

        await async_session.execute(text(revision.COLLAPSE_IDENTICAL_PRICING_SQL))

        rows = await _active_pricing(async_session, "keep-recent")
        assert [row.id for row in rows] == [newer.id]

    async def test_no_row_is_deleted_only_retired(
        self, async_session: AsyncSession, without_active_indexes: None
    ) -> None:
        await _add_pricing(async_session, "history-kept", input_price="2.0")
        await _add_pricing(async_session, "history-kept", input_price="2.0")

        await async_session.execute(text(revision.COLLAPSE_IDENTICAL_PRICING_SQL))

        total = await async_session.scalars(
            select(LLMModelPricing).where(
                LLMModelPricing.model_id
                == (await ensure_llm_model_async(async_session, "history-kept")).id
            )
        )
        assert len(list(total)) == 2, "superseded rows stay as history"

    async def test_a_single_active_row_is_untouched(self, async_session: AsyncSession) -> None:
        await _add_pricing(async_session, "lonely", input_price="2.0")

        await async_session.execute(text(revision.COLLAPSE_IDENTICAL_PRICING_SQL))

        assert len(await _active_pricing(async_session, "lonely")) == 1


@pytest.mark.unit
class TestRefuseDivergentDuplicates:
    async def test_rows_with_different_prices_are_never_collapsed(
        self, async_session: AsyncSession, without_active_indexes: None
    ) -> None:
        await _add_pricing(async_session, "divergent-price", input_price="2.0")
        await _add_pricing(async_session, "divergent-price", input_price="9.0")

        await async_session.execute(text(revision.COLLAPSE_IDENTICAL_PRICING_SQL))

        rows = await _active_pricing(async_session, "divergent-price")
        assert len(rows) == 2, "the migration must not pick a price"

    async def test_rows_with_different_units_are_never_collapsed(
        self, async_session: AsyncSession, without_active_indexes: None
    ) -> None:
        """The real ``scribe_v2`` case: audio hour versus million tokens."""
        await _add_pricing(async_session, "divergent-unit", input_price="0.22")
        await _add_pricing(
            async_session,
            "divergent-unit",
            input_price="0.22",
            unit=PricingUnitEnum.per_audio_hour,
        )

        await async_session.execute(text(revision.COLLAPSE_IDENTICAL_PRICING_SQL))

        assert len(await _active_pricing(async_session, "divergent-unit")) == 2

    async def test_divergent_rows_are_reported_by_the_detection_query(
        self, async_session: AsyncSession, without_active_indexes: None
    ) -> None:
        await _add_pricing(async_session, "reported-divergent", input_price="2.0")
        await _add_pricing(async_session, "reported-divergent", input_price="9.0")

        found = list(await async_session.execute(text(revision.DETECT_DIVERGENT_PRICING_SQL)))

        assert any(row[0] == "reported-divergent" for row in found)

    async def test_identical_rows_are_not_reported_as_divergent(
        self, async_session: AsyncSession, without_active_indexes: None
    ) -> None:
        await _add_pricing(async_session, "not-divergent", input_price="3.0")
        await _add_pricing(async_session, "not-divergent", input_price="3.0")

        found = list(await async_session.execute(text(revision.DETECT_DIVERGENT_PRICING_SQL)))

        assert all(row[0] != "not-divergent" for row in found)


@pytest.mark.unit
class TestCurrencyCollapse:
    async def test_identical_active_rates_collapse(
        self, async_session: AsyncSession, without_active_indexes: None
    ) -> None:
        for _ in range(3):
            async_session.add(
                CurrencyExchangeRate(
                    from_currency="USD",
                    to_currency="AUD",
                    rate=Decimal("1.5"),
                    is_active=True,
                )
            )
        await async_session.flush()

        await async_session.execute(text(revision.COLLAPSE_IDENTICAL_RATES_SQL))

        rows = await async_session.scalars(
            select(CurrencyExchangeRate).where(
                CurrencyExchangeRate.from_currency == "USD",
                CurrencyExchangeRate.to_currency == "AUD",
                CurrencyExchangeRate.is_active,
            )
        )
        assert len(list(rows)) == 1

    async def test_pairs_no_code_path_reads_are_retired(self, async_session: AsyncSession) -> None:
        """Only ``USD->EUR`` is ever queried; the rest are manual leftovers."""
        async_session.add(
            CurrencyExchangeRate(
                from_currency="EUR",
                to_currency="USD",
                rate=Decimal("1.05"),
                is_active=True,
            )
        )
        await async_session.flush()

        await async_session.execute(text(revision.DEACTIVATE_UNREAD_RATE_PAIRS_SQL))

        remaining = await async_session.scalars(
            select(CurrencyExchangeRate).where(CurrencyExchangeRate.is_active)
        )
        pairs = {(row.from_currency, row.to_currency) for row in remaining}
        assert pairs <= {("USD", "EUR")}


@pytest.mark.unit
class TestPartialUniqueIndexes:
    async def test_a_second_active_tariff_is_rejected(self, async_session: AsyncSession) -> None:
        """The whole point: the defect can no longer be reintroduced."""
        await async_session.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_llm_model_pricing_active "
                "ON llm_model_pricing (model_id) WHERE is_active"
            )
        )
        await _add_pricing(async_session, "guarded-model", input_price="1.0")

        with pytest.raises(IntegrityError):
            await _add_pricing(async_session, "guarded-model", input_price="7.0")

        await async_session.rollback()

    async def test_an_inactive_duplicate_is_allowed(self, async_session: AsyncSession) -> None:
        """History must remain writable — the index only constrains active rows."""
        await async_session.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_llm_model_pricing_active "
                "ON llm_model_pricing (model_id) WHERE is_active"
            )
        )
        model = await ensure_llm_model_async(async_session, "history-writable")
        for active in (False, False, True):
            async_session.add(
                LLMModelPricing(
                    model_id=model.id,
                    input_unit_price=Decimal("1"),
                    cached_input_unit_price=None,
                    output_unit_price=Decimal("2"),
                    pricing_unit=PricingUnitEnum.per_1m_tokens,
                    is_active=active,
                )
            )
        await async_session.flush()


async def _active_pricing(db: AsyncSession, model_name: str) -> list[LLMModelPricing]:
    model = await ensure_llm_model_async(db, model_name)
    rows = await db.scalars(
        select(LLMModelPricing).where(
            LLMModelPricing.model_id == model.id,
            LLMModelPricing.is_active,
        )
    )
    return list(rows)
