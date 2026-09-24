"""Admin image pricing routes hold every row to its model's family (ADR-305).

Real routes, real PostgreSQL: a row no family declares is refused, a Qwen row
without its reference-image price is refused, an OpenAI row with one is refused,
and an update that leaves the reference-image price out keeps the row's.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.image_generation.models import ImageGenerationPricing
from src.domains.llm.models import LLMProviderEnum
from src.domains.users.models import User

pytestmark = pytest.mark.integration

_ROUTE = "/api/v1/admin/image-pricing/pricing"


@pytest.fixture(autouse=True)
def _no_cross_worker_publish(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every write reloads both image caches and notifies the other workers."""
    published: list[str] = []

    async def record(cache_name: str) -> None:
        published.append(cache_name)

    monkeypatch.setattr("src.infrastructure.cache.invalidation.publish_cache_invalidation", record)
    return published


@pytest_asyncio.fixture
async def qwen_row(async_session: AsyncSession) -> ImageGenerationPricing:
    row = ImageGenerationPricing(
        provider=LLMProviderEnum.qwen,
        model="qwen-image-3.0-pro",
        quality="standard",
        size="2048x2048",
        cost_per_image_usd=Decimal("0.068761"),
        cost_per_input_image_usd=Decimal("0.002750"),
        is_active=True,
    )
    async_session.add(row)
    await async_session.commit()
    await async_session.refresh(row)
    return row


def _payload(**overrides: object) -> dict[str, object]:
    return {
        "provider": "qwen",
        "model": "qwen-image-3.0",
        "quality": "standard",
        "size": "2448x1632",
        "cost_per_image_usd": "0.024754",
        "cost_per_input_image_usd": "0.00275",
        **overrides,
    }


@pytest.mark.asyncio
async def test_a_qwen_row_is_stored_with_its_reference_image_price(
    admin_client: tuple[AsyncClient, User],
    async_session: AsyncSession,
    _no_cross_worker_publish: list[str],
) -> None:
    client, _ = admin_client

    response = await client.post(_ROUTE, json=_payload())

    assert response.status_code == 201, response.text
    assert Decimal(response.json()["cost_per_input_image_usd"]) == Decimal("0.00275")
    stored = await async_session.scalar(
        select(ImageGenerationPricing).where(ImageGenerationPricing.size == "2448x1632")
    )
    assert stored is not None and stored.cost_per_input_image_usd == Decimal("0.002750")
    assert set(_no_cross_worker_publish) == {"image_generation_pricing", "image_generation_options"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"provider": "gemini", "model": "gemini-2.5-flash-image"}, "No image client serves"),
        ({"quality": "high"}, "Quality 'high' is not offered"),
        ({"size": "4096x4096"}, "is not accepted"),
        ({"cost_per_input_image_usd": None}, "is required"),
        (
            {"provider": "openai", "model": "gpt-image-2", "quality": "low", "size": "1024x1024"},
            "must be empty",
        ),
    ],
)
async def test_a_row_its_family_refuses_is_never_stored(
    admin_client: tuple[AsyncClient, User],
    async_session: AsyncSession,
    overrides: dict[str, object],
    reason: str,
) -> None:
    client, _ = admin_client

    response = await client.post(_ROUTE, json=_payload(**overrides))

    assert response.status_code == 400
    assert reason in response.text
    assert (await async_session.scalar(select(ImageGenerationPricing.id))) is None


@pytest.mark.asyncio
async def test_an_update_without_the_reference_price_keeps_the_row_s(
    admin_client: tuple[AsyncClient, User],
    async_session: AsyncSession,
    qwen_row: ImageGenerationPricing,
) -> None:
    client, _ = admin_client

    response = await client.put(
        f"{_ROUTE}/{qwen_row.id}",
        json={"cost_per_image_usd": "0.07", "cost_per_input_image_usd": None},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (Decimal(body["cost_per_image_usd"]), Decimal(body["cost_per_input_image_usd"])) == (
        Decimal("0.07"),
        Decimal("0.00275"),
    )
    active = (
        await async_session.scalars(
            select(ImageGenerationPricing).where(ImageGenerationPricing.is_active)
        )
    ).all()
    assert len(active) == 1 and active[0].id != qwen_row.id
