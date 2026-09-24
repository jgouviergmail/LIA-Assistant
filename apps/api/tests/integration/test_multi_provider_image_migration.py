"""The ADR-305 image migration's data statements, executed on a real PostgreSQL.

The column and comments are DDL (the replay check covers them); what can go
wrong in the data is inserting over an administrator, duplicating a row across a
downgrade cycle, or leaving a preference or an image slot the previous revision
refuses. The
statements are module constants, so this test runs the SAME SQL the migration
runs.
"""

from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import get_password_hash
from src.domains.image_generation.models import ImageGenerationPricing
from src.domains.llm.models import LLMModel, LLMProviderEnum
from src.domains.llm_config.models import LLMConfigOverride
from src.domains.users.models import User

pytestmark = pytest.mark.integration

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "2026_09_23_1600-a9d3f1c7e5b2_multi_provider_image_generation.py"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("multi_provider_image", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load()
MODELS = [row["model_name"] for row in MIGRATION.CATALOGUE_ROWS]
PRICE_COUNT = sum(len(sizes) for sizes in MIGRATION.TARIFFS.values())


async def _upgrade(session: AsyncSession) -> tuple[int, int]:
    added = priced = 0
    for row in MIGRATION.CATALOGUE_ROWS:
        added += int((await session.execute(MIGRATION.INSERT_MODEL, row)).rowcount)
    for model, sizes in MIGRATION.TARIFFS.items():
        for size, output in sizes:
            result = await session.execute(
                MIGRATION.INSERT_PRICE, MIGRATION.price_params(model, size, output)
            )
            priced += int(result.rowcount)
    await session.commit()
    return added, priced


async def _active(session: AsyncSession) -> dict[tuple[str, str], ImageGenerationPricing]:
    rows = await session.scalars(
        select(ImageGenerationPricing).where(
            ImageGenerationPricing.model.in_(MODELS), ImageGenerationPricing.is_active
        )
    )
    return {(row.model, row.size): row for row in rows.all()}


@pytest.mark.asyncio
async def test_an_instance_without_qwen_images_gets_them_listed_and_priced(
    async_session: AsyncSession,
) -> None:
    assert await _upgrade(async_session) == (len(MODELS), PRICE_COUNT)

    models = (
        await async_session.scalars(select(LLMModel).where(LLMModel.model_name.in_(MODELS)))
    ).all()
    assert {(m.model_name, m.kind.value, m.capability_provenance.value) for m in models} == {
        ("qwen-image-3.0", "image", "declared"),
        ("qwen-image-3.0-pro", "image", "declared"),
    }
    prices = await _active(async_session)
    assert len(prices) == PRICE_COUNT
    assert prices[("qwen-image-3.0-pro", "2448x1632")].cost_per_image_usd == Decimal("0.068761")
    assert prices[("qwen-image-3.0-pro", "1024x1536")].cost_per_image_usd == Decimal("0.034380")
    assert {row.cost_per_input_image_usd for row in prices.values()} == {Decimal("0.002750")}


@pytest.mark.asyncio
async def test_a_price_an_administrator_set_stands(async_session: AsyncSession) -> None:
    async_session.add(
        ImageGenerationPricing(
            provider=LLMProviderEnum.qwen,
            model="qwen-image-3.0-pro",
            quality="standard",
            size="1024x1024",
            cost_per_image_usd=Decimal("0.040000"),
            cost_per_input_image_usd=Decimal("0.003000"),
            is_active=True,
        )
    )
    await async_session.commit()

    _added, priced = await _upgrade(async_session)

    assert priced == PRICE_COUNT - 1
    kept = (await _active(async_session))[("qwen-image-3.0-pro", "1024x1024")]
    assert (kept.cost_per_image_usd, kept.cost_per_input_image_usd) == (
        Decimal("0.040000"),
        Decimal("0.003000"),
    )


@pytest.mark.asyncio
async def test_a_downgrade_cycle_leaves_one_active_row_per_key(
    async_session: AsyncSession,
) -> None:
    await _upgrade(async_session)
    assert await _upgrade(async_session) == (0, 0)

    await async_session.execute(MIGRATION.DEACTIVATE_UNSERVABLE)
    await async_session.commit()
    assert await _active(async_session) == {}

    # Our deactivated rows come back rather than a second set being inserted.
    assert await _upgrade(async_session) == (0, PRICE_COUNT)
    total = await async_session.scalar(
        select(func.count())
        .select_from(ImageGenerationPricing)
        .where(ImageGenerationPricing.model.in_(MODELS))
    )
    assert total == PRICE_COUNT


@pytest.mark.asyncio
async def test_the_downgrade_leaves_no_preference_the_previous_revision_refuses(
    async_session: AsyncSession,
) -> None:
    stored = {
        "wide-2k": ("standard", "2448x1632"),
        "tall-2k": ("standard", "1632x2448"),
        "square-2k": ("low", "2048x2048"),
        "openai": ("high", "1024x1536"),
    }
    for name, (quality, size) in stored.items():
        async_session.add(
            User(
                email=f"{name}@example.com",
                hashed_password=get_password_hash("TestPass123!!"),
                full_name=name,
                is_active=True,
                is_verified=True,
                image_generation_default_quality=quality,
                image_generation_default_size=size,
            )
        )
    await async_session.commit()

    remapped = (await async_session.execute(MIGRATION.RESET_PREFERENCES)).rowcount
    await async_session.commit()

    assert remapped == 3
    rows = await async_session.execute(
        select(
            User.full_name,
            User.image_generation_default_quality,
            User.image_generation_default_size,
        ).where(User.full_name.in_(list(stored)))
    )
    assert {name: (quality, size) for name, quality, size in rows.all()} == {
        "wide-2k": ("low", "1536x1024"),
        "tall-2k": ("low", "1024x1536"),
        "square-2k": ("low", "1024x1024"),
        "openai": ("high", "1024x1536"),
    }


@pytest.mark.asyncio
async def test_the_downgrade_returns_an_image_slot_on_qwen_to_its_default(
    async_session: AsyncSession,
) -> None:
    """The previous revision cannot run a Qwen image model; a chat slot on Qwen stays."""
    async_session.add_all(
        [
            LLMConfigOverride(
                llm_type="image_generation", provider="qwen", model="qwen-image-3.0-pro"
            ),
            LLMConfigOverride(
                llm_type="response", provider="qwen", model="qwen3.7-max", temperature=0.3
            ),
        ]
    )
    await async_session.commit()

    reset = (await async_session.execute(MIGRATION.RESET_IMAGE_SLOT)).rowcount
    await async_session.commit()

    assert reset == 1
    rows = (await async_session.scalars(select(LLMConfigOverride))).all()
    assert {row.llm_type: (row.provider, row.model, row.temperature) for row in rows} == {
        "image_generation": (None, None, None),
        "response": ("qwen", "qwen3.7-max", 0.3),
    }
