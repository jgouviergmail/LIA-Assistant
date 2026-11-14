"""The Claude Fable 5.2 migration, executed on a real PostgreSQL.

The statements are module constants, so this test runs the SAME SQL the upgrade
runs: on an instance that has never heard of the model, on one where an
administrator already entered and priced it, twice in a row, and through a
downgrade/upgrade cycle.
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
    / "2026_11_11_1700-5cccb7a8d77f_seed_claude_fable_5_2.py"
)

FABLE = "claude-fable-5-2"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("seed_claude_fable_5_2", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load()


async def _upgrade(session: AsyncSession) -> tuple[int, int]:
    """The upgrade's two steps, on the session's connection."""
    added = priced = 0
    for row in MIGRATION.CATALOGUE_ROWS:
        result = await session.execute(MIGRATION.INSERT_MODEL, MIGRATION.model_params(row))
        assert isinstance(result, CursorResult)
        added += result.rowcount
    for name, tariff in MIGRATION.TARIFFS.items():
        result = await session.execute(
            MIGRATION.INSERT_TARIFF, MIGRATION.tariff_params(name, tariff)
        )
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


async def _active(session: AsyncSession, name: str) -> tuple[Decimal, Decimal | None, Decimal]:
    row = (
        await session.execute(
            select(
                LLMModelPricing.input_unit_price,
                LLMModelPricing.cached_input_unit_price,
                LLMModelPricing.output_unit_price,
            )
            .join(LLMModel, LLMModel.id == LLMModelPricing.model_id)
            .where(LLMModel.model_name == name, LLMModelPricing.is_active)
        )
    ).one()
    return row[0], row[1], row[2]


async def _tariff_rows(session: AsyncSession, name: str, *, active_only: bool = False) -> int:
    statement = (
        select(func.count())
        .select_from(LLMModelPricing)
        .join(LLMModel, LLMModel.id == LLMModelPricing.model_id)
        .where(LLMModel.model_name == name)
    )
    if active_only:
        statement = statement.where(LLMModelPricing.is_active)
    return int(await session.scalar(statement) or 0)


@pytest.mark.asyncio
async def test_an_upgraded_instance_gets_fable_5_2_and_its_list_price(
    async_session: AsyncSession,
) -> None:
    assert await _upgrade(async_session) == (1, 1)

    fable = await async_session.scalar(select(LLMModel).where(LLMModel.model_name == FABLE))
    assert fable is not None
    assert fable.provider == LLMProviderEnum.anthropic
    assert fable.capability_provenance.value == "verified"
    assert (fable.max_input_tokens, fable.max_output_tokens) == (1_000_000, 128_000)
    # No ``none``: adaptive thinking cannot be switched off on this model.
    assert fable.reasoning_enum_values == ["low", "medium", "high", "xhigh", "max"]
    assert fable.is_reasoning_model is True and fable.supports_vision is True
    assert fable.supports_temperature is False and fable.supports_top_p is False
    assert fable.is_active is True
    assert await _active(async_session, FABLE) == (Decimal("8"), Decimal("0.2"), Decimal("40"))
    dated = await async_session.scalar(
        select(LLMModelPricing.effective_from)
        .join(LLMModel, LLMModel.id == LLMModelPricing.model_id)
        .where(LLMModel.model_name == FABLE, LLMModelPricing.is_active)
    )
    assert dated == MIGRATION.EFFECTIVE_FROM_AT


@pytest.mark.asyncio
async def test_a_row_and_a_price_an_administrator_entered_stand(
    async_session: AsyncSession,
) -> None:
    await create_llm_pricing_async(
        async_session,
        model_name=FABLE,
        input_price=Decimal("9"),
        output_price=Decimal("45"),
        cached_input_price=Decimal("0.9"),
        provider=LLMProviderEnum.anthropic,
        is_active=True,
    )
    await async_session.commit()
    before = await async_session.scalar(select(LLMModel).where(LLMModel.model_name == FABLE))
    assert before is not None
    entered = (before.max_input_tokens, before.capability_provenance.value)

    assert await _upgrade(async_session) == (0, 0)

    await async_session.refresh(before)
    assert (before.max_input_tokens, before.capability_provenance.value) == entered
    assert await _active(async_session, FABLE) == (Decimal("9"), Decimal("0.9"), Decimal("45"))
    assert await _tariff_rows(async_session, FABLE) == 1


@pytest.mark.asyncio
async def test_a_second_run_changes_nothing_and_a_downgrade_retires_only_the_tariff(
    async_session: AsyncSession,
) -> None:
    await _upgrade(async_session)

    assert await _upgrade(async_session) == (0, 0)

    await _downgrade(async_session)
    assert await _tariff_rows(async_session, FABLE, active_only=True) == 0
    # The catalogue row stays: an administrator may have set a slot on it.
    assert await async_session.scalar(select(LLMModel.id).where(LLMModel.model_name == FABLE))

    # Up again: the row the downgrade retired comes back, none is duplicated.
    assert await _upgrade(async_session) == (0, 1)
    assert await _active(async_session, FABLE) == (Decimal("8"), Decimal("0.2"), Decimal("40"))
    assert await _tariff_rows(async_session, FABLE) == 1
