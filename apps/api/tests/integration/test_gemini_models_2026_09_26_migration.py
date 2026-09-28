"""The 2026-09-26 Gemini models migration, executed on a real PostgreSQL.

Its whole behaviour is two conditional INSERTs; the statements are module
constants, so this test runs the SAME SQL the upgrade runs against an empty
catalogue, against a row and a price an administrator set, twice in a row, and
through a downgrade/upgrade cycle. One tariff carries no cache price: the NULL
must reach the column as the absence of a price, never as zero.
"""

from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.llm.models import LLMModel, LLMModelPricing, LLMProviderEnum
from tests.helpers.llm_helpers import create_llm_pricing_async

pytestmark = pytest.mark.integration

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "2026_09_26_1700-7b3e9d1f5c2a_seed_gemini_models_2026_09_26.py"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("seed_gemini_models_2026_09_26", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load()
NAMES = [row["model_name"] for row in MIGRATION.CATALOGUE_ROWS]


async def _upgrade(session: AsyncSession) -> tuple[int, int]:
    added = priced = 0
    for row in MIGRATION.CATALOGUE_ROWS:
        result = await session.execute(MIGRATION.INSERT_MODEL, MIGRATION.model_params(row))
        assert isinstance(result, CursorResult)
        added += result.rowcount
    for name in MIGRATION.TARIFFS:
        result = await session.execute(MIGRATION.INSERT_TARIFF, MIGRATION.tariff_params(name))
        assert isinstance(result, CursorResult)
        priced += result.rowcount
    await session.commit()
    return added, priced


async def _downgrade(session: AsyncSession) -> None:
    for name in MIGRATION.TARIFFS:
        await session.execute(
            MIGRATION.RETIRE_TARIFF,
            {"model_name": name, "effective_from": MIGRATION.EFFECTIVE_FROM_AT},
        )
    await session.commit()


async def _active_prices(
    session: AsyncSession,
) -> dict[str, tuple[Decimal, Decimal | None, Decimal]]:
    rows = await session.execute(
        select(
            LLMModel.model_name,
            LLMModelPricing.input_unit_price,
            LLMModelPricing.cached_input_unit_price,
            LLMModelPricing.output_unit_price,
        )
        .join(LLMModelPricing, LLMModelPricing.model_id == LLMModel.id)
        .where(LLMModel.model_name.in_(NAMES), LLMModelPricing.is_active)
    )
    return {name: (i, c, o) for name, i, c, o in rows.all()}


@pytest.mark.asyncio
async def test_an_instance_without_the_models_gets_them_curated_and_priced(
    async_session: AsyncSession,
) -> None:
    assert await _upgrade(async_session) == (len(NAMES), len(NAMES))

    models = {
        m.model_name: m
        for m in (
            await async_session.scalars(select(LLMModel).where(LLMModel.model_name.in_(NAMES)))
        ).all()
    }
    assert set(models) == set(NAMES)
    assert {m.capability_provenance.value for m in models.values()} == {"verified"}
    assert models["gemini-3.1-flash-lite"].kind.value == "chat"
    assert models["gemini-3.1-flash-lite"].max_input_tokens == 1_048_576
    assert {models[name].kind.value for name in NAMES[1:]} == {"tts"}
    prices = await _active_prices(async_session)
    assert prices["gemini-3.1-flash-lite"] == (Decimal("0.25"), Decimal("0.025"), Decimal("1.5"))
    assert prices["gemini-3.8-flash-tts"] == (Decimal("0.5"), Decimal("0.125"), Decimal("9"))
    assert prices["gemini-3.1-flash-tts-preview"] == (Decimal("1"), None, Decimal("20"))


@pytest.mark.asyncio
async def test_what_an_administrator_set_stands(async_session: AsyncSession) -> None:
    """An admin created gemini-3.8-flash-tts by hand at its own price before the deploy."""
    await create_llm_pricing_async(
        async_session,
        model_name="gemini-3.8-flash-tts",
        input_price=Decimal("0.60"),
        output_price=Decimal("10.00"),
        cached_input_price=None,
        provider=LLMProviderEnum.gemini,
        is_active=True,
    )
    await async_session.commit()

    added, priced = await _upgrade(async_session)

    assert (added, priced) == (len(NAMES) - 1, len(NAMES) - 1)
    prices = await _active_prices(async_session)
    assert prices["gemini-3.8-flash-tts"] == (Decimal("0.60"), None, Decimal("10.00"))
    active_rows = await async_session.scalar(
        select(func.count())
        .select_from(LLMModelPricing)
        .join(LLMModel, LLMModel.id == LLMModelPricing.model_id)
        .where(LLMModel.model_name == "gemini-3.8-flash-tts", LLMModelPricing.is_active)
    )
    assert active_rows == 1


@pytest.mark.asyncio
async def test_a_second_run_and_a_downgrade_cycle_leave_one_active_tariff_each(
    async_session: AsyncSession,
) -> None:
    await _upgrade(async_session)
    assert await _upgrade(async_session) == (0, 0)

    await _downgrade(async_session)
    assert await _active_prices(async_session) == {}

    # The retired row comes back rather than a second one being inserted.
    assert await _upgrade(async_session) == (0, len(NAMES))
    assert set(await _active_prices(async_session)) == set(NAMES)
    total_rows = await async_session.scalar(
        select(func.count())
        .select_from(LLMModelPricing)
        .join(LLMModel, LLMModel.id == LLMModelPricing.model_id)
        .where(LLMModel.model_name.in_(NAMES))
    )
    assert total_rows == len(NAMES)
