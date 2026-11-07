"""The 2026-11-06 extraction migration, executed on a real PostgreSQL.

Its whole behaviour is conditional writes; the statements are module constants, so this test runs
the SAME SQL the upgrade runs: on an instance that lacks the rows, on one an administrator priced,
twice in a row, and through a downgrade and a second upgrade.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "2026_11_07_0100-d2f6b8c4e1a7_carry_extracted_models.py"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("carry_extracted_models", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load()
TERRA = MIGRATION.TERRA["model_name"]
DRAMA = MIGRATION.DRAMA_MODEL
FLARES = ("gpt-image-2.5-flare", "gpt-image-2.6-flare")


async def _migrate(session: AsyncSession, step: Callable[[], None]) -> None:
    """Run one direction of the revision on the test's own connection."""

    def _run(sync_session: Any) -> None:
        context = MigrationContext.configure(sync_session.connection())
        with Operations.context(context):
            step()

    await session.run_sync(_run)


async def _clear(session: AsyncSession) -> None:
    """An instance that holds none of it."""
    await session.execute(
        text(
            "DELETE FROM llm_model_pricing WHERE model_id IN "
            "(SELECT id FROM llm_models WHERE model_name = ANY(:names))"
        ),
        {"names": [TERRA, DRAMA]},
    )
    await session.execute(text("DELETE FROM llm_models WHERE model_name = :name"), {"name": TERRA})
    await session.execute(
        text("DELETE FROM image_generation_pricing WHERE model = ANY(:names)"),
        {"names": list(FLARES)},
    )


async def _drama_priced_at(session: AsyncSession, price: str) -> None:
    """The fish-audio row, its one tariff at ``price``."""
    await session.execute(
        text(
            "INSERT INTO llm_models (id, created_at, updated_at, provider, model_name, "
            "max_input_tokens, max_output_tokens, supports_tools, supports_structured_output, "
            "supports_strict_mode, supports_streaming, supports_vision, is_reasoning_model, "
            "supports_temperature, supports_top_p, supports_frequency_penalty, "
            "supports_presence_penalty, kind, is_active, capability_provenance) "
            "VALUES (gen_random_uuid(), NOW(), NOW(), 'fishaudio', :name, 8192, 1, false, false, "
            "false, true, false, false, false, false, false, false, 'tts', true, 'declared') "
            "ON CONFLICT (model_name) DO NOTHING"
        ),
        {"name": DRAMA},
    )
    await session.execute(
        text(
            "INSERT INTO llm_model_pricing (id, model_id, input_unit_price, "
            "cached_input_unit_price, output_unit_price, pricing_unit, effective_from, "
            "is_active, created_at, updated_at) "
            "SELECT :id, id, CAST(:price AS numeric), NULL, 0, 'per_1m_tokens', "
            "'2026-10-13T00:00:00+00:00', true, NOW(), NOW() "
            "FROM llm_models WHERE model_name = :name"
        ),
        {"id": uuid4(), "price": price, "name": DRAMA},
    )


async def _active_inputs(session: AsyncSession, model: str) -> list[Decimal]:
    rows = await session.execute(
        text(
            "SELECT p.input_unit_price FROM llm_model_pricing p "
            "JOIN llm_models m ON m.id = p.model_id "
            "WHERE m.model_name = :name AND p.is_active"
        ),
        {"name": model},
    )
    return [row[0] for row in rows]


async def _active_images(session: AsyncSession) -> int:
    count = await session.execute(
        text(
            "SELECT count(*) FROM image_generation_pricing "
            "WHERE model = ANY(:names) AND is_active"
        ),
        {"names": list(FLARES)},
    )
    return int(count.scalar_one())


async def test_an_upgraded_instance_gains_what_it_lacks(async_session: AsyncSession) -> None:
    await _clear(async_session)
    await _drama_priced_at(async_session, "10")

    await _migrate(async_session, MIGRATION.upgrade)

    assert await _active_inputs(async_session, TERRA) == [Decimal("1.000000")]
    assert await _active_inputs(async_session, DRAMA) == [Decimal("50.000000")]
    assert await _active_images(async_session) == len(MIGRATION.IMAGE_PRICES)


async def test_a_price_an_administrator_set_stands(async_session: AsyncSession) -> None:
    await _clear(async_session)
    await _drama_priced_at(async_session, "22")

    await _migrate(async_session, MIGRATION.upgrade)

    assert await _active_inputs(async_session, DRAMA) == [Decimal("22.000000")]


async def test_an_image_price_an_administrator_set_stands(async_session: AsyncSession) -> None:
    await _clear(async_session)
    first = MIGRATION.IMAGE_PRICES[0]
    await async_session.execute(
        text(
            "INSERT INTO image_generation_pricing (id, provider, model, quality, size, "
            "cost_per_image_usd, effective_from, is_active, created_at, updated_at) "
            "VALUES (:id, 'openai', :model, :quality, :size, 0.5, "
            "'2026-10-01T00:00:00+00:00', true, NOW(), NOW())"
        ),
        {"id": uuid4(), "model": first[0], "quality": first[1], "size": first[2]},
    )

    await _migrate(async_session, MIGRATION.upgrade)

    held = await async_session.execute(
        text(
            "SELECT cost_per_image_usd FROM image_generation_pricing "
            "WHERE model = :model AND quality = :quality AND size = :size AND is_active"
        ),
        {"model": first[0], "quality": first[1], "size": first[2]},
    )
    assert [row[0] for row in held] == [Decimal("0.500000")]


async def test_running_it_twice_adds_nothing(async_session: AsyncSession) -> None:
    await _clear(async_session)
    await _drama_priced_at(async_session, "10")

    await _migrate(async_session, MIGRATION.upgrade)
    await _migrate(async_session, MIGRATION.upgrade)

    assert await _active_inputs(async_session, TERRA) == [Decimal("1.000000")]
    assert await _active_inputs(async_session, DRAMA) == [Decimal("50.000000")]
    assert await _active_images(async_session) == len(MIGRATION.IMAGE_PRICES)


async def test_a_downgrade_retires_its_prices_and_keeps_the_catalogue(
    async_session: AsyncSession,
) -> None:
    await _clear(async_session)
    await _drama_priced_at(async_session, "10")
    await _migrate(async_session, MIGRATION.upgrade)

    await _migrate(async_session, MIGRATION.downgrade)

    assert await _active_inputs(async_session, TERRA) == []
    assert await _active_images(async_session) == 0
    assert await _active_inputs(async_session, DRAMA) == [Decimal("50.000000")]
    known = await async_session.execute(
        text("SELECT count(*) FROM llm_models WHERE model_name = :name"), {"name": TERRA}
    )
    assert known.scalar_one() == 1

    await _migrate(async_session, MIGRATION.upgrade)

    assert await _active_inputs(async_session, TERRA) == [Decimal("1.000000")]
    assert await _active_images(async_session) == len(MIGRATION.IMAGE_PRICES)
