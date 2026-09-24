"""Unit tests for ImageGenerationPricingService: what one call costs (ADR-305)."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.image_generation.pricing_service import (
    ImageGenerationPricingService,
    ImagePrice,
)

_RATE = "src.domains.image_generation.pricing_service.get_cached_usd_eur_rate"


@pytest.fixture(autouse=True)
def _prices() -> Iterator[None]:
    ImageGenerationPricingService._pricing_cache = {
        "gpt-image-2:low:1024x1024": ImagePrice(Decimal("0.011"), None),
        "qwen-image-3.0-pro:standard:2448x1632": ImagePrice(
            Decimal("0.068761"), Decimal("0.00275")
        ),
    }
    yield
    ImageGenerationPricingService._pricing_cache = {}


@pytest.mark.unit
class TestCostOfCall:
    """Output images, plus reference images where the family bills them."""

    def test_a_generation_costs_its_output_at_the_shared_rate(self) -> None:
        with patch(_RATE, return_value=0.85):
            usd, eur, rate = ImageGenerationPricingService.cost_of_call(
                model="gpt-image-2",
                quality="low",
                size="1024x1024",
                image_count=1,
                input_image_count=0,
            )
        assert (usd, eur, rate) == (
            Decimal("0.011"),
            Decimal("0.011") * Decimal("0.85"),
            Decimal("0.85"),
        )

    def test_a_qwen_edit_adds_its_reference_image(self) -> None:
        with patch(_RATE, return_value=1.0):
            usd, _, _ = ImageGenerationPricingService.cost_of_call(
                model="qwen-image-3.0-pro",
                quality="standard",
                size="2448x1632",
                image_count=1,
                input_image_count=1,
            )
        assert usd == Decimal("0.068761") + Decimal("0.00275")

    def test_an_openai_edit_prices_no_reference_image(self) -> None:
        """OpenAI bills an edit's input as tokens: the row declares no per-image price."""
        with patch(_RATE, return_value=1.0):
            usd, _, _ = ImageGenerationPricingService.cost_of_call(
                model="gpt-image-2",
                quality="low",
                size="1024x1024",
                image_count=1,
                input_image_count=1,
            )
        assert usd == Decimal("0.011")

    def test_an_unpriced_key_costs_zero_and_says_so(self) -> None:
        with patch(_RATE, return_value=0.9):
            usd, eur, rate = ImageGenerationPricingService.cost_of_call(
                model="unknown-model",
                quality="low",
                size="1024x1024",
                image_count=1,
                input_image_count=0,
            )
        assert (usd, eur, rate) == (Decimal("0"), Decimal("0"), Decimal("0.9"))


@pytest.mark.unit
class TestLoadPricingCache:
    """The cache reads both prices and no currency API."""

    async def test_load_reads_the_output_and_the_reference_image_price(self) -> None:
        rows = [
            SimpleNamespace(
                model="qwen-image-3.0",
                quality="standard",
                size="1024x1024",
                cost_per_image_usd=Decimal("0.024754"),
                cost_per_input_image_usd=Decimal("0.00275"),
            ),
            SimpleNamespace(
                model="gpt-image-2",
                quality="high",
                size="1024x1536",
                cost_per_image_usd=Decimal("0.25"),
                cost_per_input_image_usd=None,
            ),
        ]
        with patch(
            "src.domains.image_generation.pricing_service.ImageGenerationPricingRepository"
        ) as repo_cls:
            repo_cls.return_value.get_active_pricing = AsyncMock(return_value=rows)
            await ImageGenerationPricingService.load_pricing_cache(AsyncMock())

        assert ImageGenerationPricingService.get_price(
            "qwen-image-3.0", "standard", "1024x1024"
        ) == ImagePrice(Decimal("0.024754"), Decimal("0.00275"))
        assert ImageGenerationPricingService.get_price(
            "gpt-image-2", "high", "1024x1536"
        ) == ImagePrice(Decimal("0.25"), None)
        assert ImageGenerationPricingService.is_cache_loaded()
