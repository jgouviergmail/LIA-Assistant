"""The 2026-09-23 price corrections migration, executed on a real PostgreSQL.

Its statements are module constants, so this test runs the SAME SQL the
upgrade and the downgrade run: against a tariff still at a value LIA shipped,
against a price an administrator set, twice in a row, and through a
downgrade/upgrade cycle -- under the partial unique index that allows ONE active
tariff per model.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.google_api.models import GoogleApiPricing
from src.domains.image_generation.models import ImageGenerationPricing
from src.domains.llm.models import LLMModel, LLMModelPricing, LLMProviderEnum
from tests.helpers.llm_helpers import create_llm_pricing_async

pytestmark = pytest.mark.integration

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "2026_09_23_2000-d5f8b2a6c9e3_published_price_corrections.py"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("price_corrections", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load()
CORRECTIONS = {c.model_name: c for c in MIGRATION.CORRECTIONS}


async def _upgrade(session: AsyncSession) -> dict[str, int]:
    """Run the upgrade's statements; count what changed, per table."""
    counts = {"tariffs": 0, "images": 0, "maps": 0}
    for correction in MIGRATION.CORRECTIONS:
        for shipped in correction.shipped:
            result = await session.execute(
                MIGRATION.RETIRE_SHIPPED, MIGRATION.tariff_params(correction.model_name, shipped)
            )
            for (model_id,) in result.all():
                await session.execute(
                    MIGRATION.INSERT_PUBLISHED, MIGRATION.published_params(model_id, correction)
                )
                counts["tariffs"] += 1
    for image in MIGRATION.IMAGE_CORRECTIONS:
        result = await session.execute(
            MIGRATION.RETIRE_SHIPPED_IMAGE,
            {**MIGRATION.image_key(image), "price": Decimal(image.shipped)},
        )
        for (provider,) in result.all():
            await session.execute(
                MIGRATION.INSERT_PUBLISHED_IMAGE,
                {
                    **MIGRATION.image_key(image),
                    "provider": provider,
                    "price": Decimal(image.published),
                    "effective_from": MIGRATION.EFFECTIVE_FROM_AT,
                },
            )
            counts["images"] += 1
    for row in MIGRATION.GOOGLE_PRICES:
        if row.shipped is None:
            statement = MIGRATION.INSERT_GOOGLE
            params = {**MIGRATION.google_params(row), "effective_from": MIGRATION.EFFECTIVE_FROM_AT}
        else:
            statement = MIGRATION.CORRECT_GOOGLE
            params = {
                **MIGRATION.google_params(row),
                "shipped": Decimal(row.shipped),
                "shipped_sku": row.shipped_sku,
            }
        counts["maps"] += int((await session.execute(statement, params)).rowcount)
    await session.commit()
    return counts


async def _downgrade(session: AsyncSession) -> None:
    for correction in MIGRATION.CORRECTIONS:
        result = await session.execute(
            MIGRATION.RETIRE_PUBLISHED,
            {"model_name": correction.model_name, "effective_from": MIGRATION.EFFECTIVE_FROM_AT},
        )
        for (model_id,) in result.all():
            await session.execute(
                MIGRATION.RESTORE_PREVIOUS,
                {"model_id": model_id, "effective_from": MIGRATION.EFFECTIVE_FROM_AT},
            )
    for image in MIGRATION.IMAGE_CORRECTIONS:
        key = {**MIGRATION.image_key(image), "effective_from": MIGRATION.EFFECTIVE_FROM_AT}
        if (await session.execute(MIGRATION.RETIRE_PUBLISHED_IMAGE, key)).all():
            await session.execute(MIGRATION.RESTORE_PREVIOUS_IMAGE, key)
    for row in MIGRATION.GOOGLE_PRICES:
        if row.shipped is None:
            await session.execute(
                MIGRATION.DELETE_GOOGLE,
                {
                    "api_name": row.api_name,
                    "endpoint": row.endpoint,
                    "effective_from": MIGRATION.EFFECTIVE_FROM_AT,
                },
            )
        else:
            await session.execute(
                MIGRATION.CORRECT_GOOGLE,
                {
                    "api_name": row.api_name,
                    "endpoint": row.endpoint,
                    "sku_name": row.shipped_sku,
                    "price": Decimal(row.shipped),
                    "shipped": Decimal(row.price),
                    "shipped_sku": row.sku_name,
                },
            )
    await session.commit()


async def _active(session: AsyncSession, model: str) -> LLMModelPricing:
    rows = (
        await session.scalars(
            select(LLMModelPricing)
            .join(LLMModel, LLMModel.id == LLMModelPricing.model_id)
            .where(LLMModel.model_name == model, LLMModelPricing.is_active)
        )
    ).all()
    assert len(rows) == 1, f"{model}: {len(rows)} active tariffs"
    return rows[0]


def _prices(row: LLMModelPricing) -> tuple[Decimal, Decimal | None, Decimal]:
    return (row.input_unit_price, row.cached_input_unit_price, row.output_unit_price)


async def _ship(session: AsyncSession, model: str, provider: LLMProviderEnum) -> None:
    """Stand an instance's tariff at the first value LIA shipped for ``model``."""
    shipped = CORRECTIONS[model].shipped[0]
    await create_llm_pricing_async(
        session,
        model_name=model,
        input_price=Decimal(shipped.input),
        output_price=Decimal(shipped.output),
        cached_input_price=None if shipped.cached is None else Decimal(shipped.cached),
        provider=provider,
        is_active=True,
    )


@pytest.mark.asyncio
async def test_a_shipped_value_is_replaced_by_the_published_price(
    async_session: AsyncSession,
) -> None:
    await _ship(async_session, "gpt-5.6-sol", LLMProviderEnum.openai)
    await _ship(async_session, "gemini-2.5-pro-preview-tts", LLMProviderEnum.gemini)

    assert (await _upgrade(async_session))["tariffs"] == 2

    assert _prices(await _active(async_session, "gpt-5.6-sol")) == (
        Decimal("4"),
        Decimal("0.4"),
        Decimal("20"),
    )
    # A speech model has no cache price: the column is NULL, not zero.
    assert _prices(await _active(async_session, "gemini-2.5-pro-preview-tts")) == (
        Decimal("1"),
        None,
        Decimal("20"),
    )


@pytest.mark.asyncio
async def test_the_legacy_deepseek_name_gets_the_flash_windows(
    async_session: AsyncSession,
) -> None:
    await _ship(async_session, "deepseek-v4-flash", LLMProviderEnum.deepseek)

    assert (await _upgrade(async_session))["tariffs"] == 1

    row = await _active(async_session, "deepseek-v4-flash")
    assert _prices(row) == (Decimal("0.15"), Decimal("0.003"), Decimal("0.6"))
    assert row.time_slots == CORRECTIONS["deepseek-v4-flash"].time_slots


@pytest.mark.asyncio
async def test_what_an_administrator_set_stands(async_session: AsyncSession) -> None:
    """An operator priced qwen3-max's cache themselves: not a value LIA shipped."""
    await create_llm_pricing_async(
        async_session,
        model_name="qwen3-max",
        input_price=Decimal("0.359"),
        output_price=Decimal("1.434"),
        cached_input_price=Decimal("0.1"),
        provider=LLMProviderEnum.qwen,
        is_active=True,
    )

    assert (await _upgrade(async_session))["tariffs"] == 0
    assert _prices(await _active(async_session, "qwen3-max")) == (
        Decimal("0.359"),
        Decimal("0.1"),
        Decimal("1.434"),
    )


@pytest.mark.asyncio
async def test_a_second_run_and_a_downgrade_cycle_keep_one_active_tariff(
    async_session: AsyncSession,
) -> None:
    await _ship(async_session, "qwen3.7-plus", LLMProviderEnum.qwen)
    assert (await _upgrade(async_session))["tariffs"] == 1
    assert (await _upgrade(async_session))["tariffs"] == 0

    await _downgrade(async_session)
    assert _prices(await _active(async_session, "qwen3.7-plus")) == (
        Decimal("0.276"),
        Decimal("0.056"),
        Decimal("1.101"),
    )

    # The corrected row comes back rather than a second one being inserted.
    assert (await _upgrade(async_session))["tariffs"] == 1
    assert _prices(await _active(async_session, "qwen3.7-plus"))[1] == Decimal("0.0552")
    total = await async_session.scalar(
        select(func.count())
        .select_from(LLMModelPricing)
        .join(LLMModel, LLMModel.id == LLMModelPricing.model_id)
        .where(LLMModel.model_name == "qwen3.7-plus")
    )
    assert total == 2


async def _image_price(session: AsyncSession, quality: str, size: str) -> Decimal:
    rows = (
        await session.scalars(
            select(ImageGenerationPricing.cost_per_image_usd).where(
                ImageGenerationPricing.model == MIGRATION.IMAGE_MODEL,
                ImageGenerationPricing.quality == quality,
                ImageGenerationPricing.size == size,
                ImageGenerationPricing.is_active,
            )
        )
    ).all()
    assert len(rows) == 1, f"{quality} {size}: {len(rows)} active prices"
    return rows[0]


def _image_row(quality: str, size: str, price: str) -> ImageGenerationPricing:
    return ImageGenerationPricing(
        provider=LLMProviderEnum.openai,
        model=MIGRATION.IMAGE_MODEL,
        quality=quality,
        size=size,
        cost_per_image_usd=Decimal(price),
        cost_per_input_image_usd=None,
        effective_from=datetime.now(UTC),
        is_active=True,
    )


@pytest.mark.asyncio
async def test_gpt_image_2_leaves_the_price_copied_from_gpt_image_1(
    async_session: AsyncSession,
) -> None:
    """The copied price is corrected; a price an operator set stands; a downgrade restores."""
    async_session.add(_image_row("high", "1024x1024", "0.167"))  # shipped (gpt-image-1's)
    async_session.add(_image_row("low", "1024x1024", "0.009"))  # an operator's own price
    await async_session.commit()

    assert (await _upgrade(async_session))["images"] == 1
    assert await _image_price(async_session, "high", "1024x1024") == Decimal("0.211")
    assert await _image_price(async_session, "low", "1024x1024") == Decimal("0.009")
    assert (await _upgrade(async_session))["images"] == 0

    await _downgrade(async_session)
    assert await _image_price(async_session, "high", "1024x1024") == Decimal("0.167")


async def _maps_prices(session: AsyncSession) -> dict[str, tuple[str, Decimal]]:
    rows = await session.execute(
        select(
            GoogleApiPricing.endpoint, GoogleApiPricing.sku_name, GoogleApiPricing.cost_per_1000_usd
        ).where(GoogleApiPricing.is_active)
    )
    return {endpoint: (sku, price) for endpoint, sku, price in rows.all()}


@pytest.mark.asyncio
async def test_street_view_is_corrected_and_the_routes_tiers_are_added(
    async_session: AsyncSession,
) -> None:
    """An instance still holding the shipped Maps rows, as production does."""
    shipped = [
        ("street_view", "/streetview", "Street View Static", "2"),
        ("routes", "/directions/v2:computeRoutes", "Compute Routes", "5"),
        ("routes", "/distanceMatrix/v2:computeRouteMatrix", "Route Matrix", "5"),
    ]
    for api_name, endpoint, sku_name, price in shipped:
        async_session.add(
            GoogleApiPricing(
                api_name=api_name,
                endpoint=endpoint,
                sku_name=sku_name,
                cost_per_1000_usd=Decimal(price),
                effective_from=datetime.now(UTC),
                is_active=True,
            )
        )
    await async_session.commit()

    assert (await _upgrade(async_session))["maps"] == 7
    prices = await _maps_prices(async_session)
    assert prices["/streetview"] == ("Street View Static", Decimal("7"))
    assert prices["/directions/v2:computeRoutes:enterprise"] == (
        "Compute Routes Enterprise",
        Decimal("15"),
    )
    assert prices["/distanceMatrix/v2:computeRouteMatrix:pro"] == (
        "Compute Route Matrix Pro",
        Decimal("10"),
    )
    assert (await _upgrade(async_session))["maps"] == 0

    await _downgrade(async_session)
    prices = await _maps_prices(async_session)
    assert prices["/streetview"] == ("Street View Static", Decimal("2"))
    assert prices["/directions/v2:computeRoutes"] == ("Compute Routes", Decimal("5"))
    assert "/directions/v2:computeRoutes:enterprise" not in prices
