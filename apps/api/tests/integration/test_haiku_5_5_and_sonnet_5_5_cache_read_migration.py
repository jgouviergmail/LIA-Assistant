"""The 2026-10-08 Claude migration, executed on a real PostgreSQL.

The statements are module constants, so this test runs the SAME SQL the upgrade
runs: against an instance holding the Sonnet 5.5 tariff LIA shipped, against a
price an administrator set, twice in a row, and through a downgrade/upgrade
cycle.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
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
    / "2026_10_08_1200-36ecac9a51ea_haiku_5_5_and_sonnet_5_5_cache_read.py"
)

SONNET = "claude-sonnet-5-5"
HAIKU = "claude-haiku-5-5"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("haiku_5_5_and_sonnet_cache_read", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load()


async def _upgrade(session: AsyncSession) -> tuple[int, int, int]:
    """The upgrade's three steps, on the session's connection."""
    added = priced = corrected = 0
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
    for correction in MIGRATION.CORRECTIONS:
        for shipped in correction.shipped:
            retired = (
                await session.execute(
                    MIGRATION.RETIRE_SHIPPED,
                    MIGRATION.tariff_params(correction.model_name, shipped),
                )
            ).scalar_one_or_none()
            if retired is not None:
                await session.execute(
                    MIGRATION.INSERT_PUBLISHED,
                    {
                        **MIGRATION.tariff_params(correction.model_name, correction.published),
                        "model_id": retired,
                    },
                )
                corrected += 1
                break
    await session.commit()
    return added, priced, corrected


async def _downgrade(session: AsyncSession) -> None:
    for name in MIGRATION.TARIFFS:
        await session.execute(
            MIGRATION.RETIRE_TARIFF,
            {"model_name": name, "effective_from": MIGRATION.EFFECTIVE_FROM_AT},
        )
    for correction in MIGRATION.CORRECTIONS:
        model_id = (
            await session.execute(
                MIGRATION.RETIRE_PUBLISHED,
                {
                    "model_name": correction.model_name,
                    "effective_from": MIGRATION.EFFECTIVE_FROM_AT,
                },
            )
        ).scalar_one_or_none()
        if model_id is not None:
            await session.execute(
                MIGRATION.RESTORE_PREVIOUS,
                {"model_id": model_id, "effective_from": MIGRATION.EFFECTIVE_FROM_AT},
            )
    await session.commit()


async def _ship_sonnet_tariff(session: AsyncSession) -> None:
    """The state ``fc0147eeb095`` left: Sonnet 5.5 at 2 / 0.2 / 10, dated 2026-09-30."""
    pricing = await create_llm_pricing_async(
        session,
        model_name=SONNET,
        input_price=Decimal("2"),
        output_price=Decimal("10"),
        cached_input_price=Decimal("0.2"),
        provider=LLMProviderEnum.anthropic,
        is_active=True,
    )
    pricing.effective_from = datetime(2026, 9, 30, tzinfo=UTC)
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


async def _tariff_rows(session: AsyncSession, name: str) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(LLMModelPricing)
        .join(LLMModel, LLMModel.id == LLMModelPricing.model_id)
        .where(LLMModel.model_name == name)
    )
    return int(count or 0)


@pytest.mark.asyncio
async def test_an_upgraded_instance_gets_haiku_and_sonnets_published_cache_read(
    async_session: AsyncSession,
) -> None:
    await _ship_sonnet_tariff(async_session)

    assert await _upgrade(async_session) == (1, 1, 1)

    haiku = await async_session.scalar(select(LLMModel).where(LLMModel.model_name == HAIKU))
    assert haiku is not None
    assert haiku.capability_provenance.value == "verified"
    assert (haiku.max_input_tokens, haiku.max_output_tokens) == (1_000_000, 128_000)
    assert haiku.reasoning_enum_values == ["none", "low", "medium", "high", "xhigh", "max"]
    assert await _active(async_session, HAIKU) == (
        Decimal("0.1"),
        Decimal("0.01"),
        Decimal("0.5"),
    )
    assert await _active(async_session, SONNET) == (Decimal("2"), Decimal("0.1"), Decimal("10"))
    # The shipped row is kept, retired: price history is never deleted.
    assert await _tariff_rows(async_session, SONNET) == 2


@pytest.mark.asyncio
async def test_a_sonnet_price_an_administrator_set_stands(async_session: AsyncSession) -> None:
    await create_llm_pricing_async(
        async_session,
        model_name=SONNET,
        input_price=Decimal("2"),
        output_price=Decimal("10"),
        cached_input_price=Decimal("0.15"),
        provider=LLMProviderEnum.anthropic,
        is_active=True,
    )
    await async_session.commit()

    assert await _upgrade(async_session) == (1, 1, 0)

    assert await _active(async_session, SONNET) == (Decimal("2"), Decimal("0.15"), Decimal("10"))
    assert await _tariff_rows(async_session, SONNET) == 1


@pytest.mark.asyncio
async def test_a_second_run_changes_nothing_and_a_downgrade_restores_the_shipped_tariff(
    async_session: AsyncSession,
) -> None:
    await _ship_sonnet_tariff(async_session)
    await _upgrade(async_session)

    assert await _upgrade(async_session) == (0, 0, 0)

    await _downgrade(async_session)
    assert await _active(async_session, SONNET) == (Decimal("2"), Decimal("0.2"), Decimal("10"))
    haiku_active = await async_session.scalar(
        select(func.count())
        .select_from(LLMModelPricing)
        .join(LLMModel, LLMModel.id == LLMModelPricing.model_id)
        .where(LLMModel.model_name == HAIKU, LLMModelPricing.is_active)
    )
    assert haiku_active == 0

    # Up again: the rows the downgrade retired come back, none is duplicated.
    assert await _upgrade(async_session) == (0, 1, 1)
    assert await _active(async_session, SONNET) == (Decimal("2"), Decimal("0.1"), Decimal("10"))
    assert await _tariff_rows(async_session, SONNET) == 2
    assert await _tariff_rows(async_session, HAIKU) == 1
