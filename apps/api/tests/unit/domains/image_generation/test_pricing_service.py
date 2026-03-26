"""Unit tests for ImageGenerationPricingService.

Tests the in-memory pricing cache: loading, cost lookups, and edge cases.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.image_generation.pricing_service import ImageGenerationPricingService


@pytest.mark.unit
class TestGetCostPerImage:
    """Tests for ImageGenerationPricingService.get_cost_per_image()."""

    def setup_method(self) -> None:
        """Seed the cache with known pricing for tests."""
        ImageGenerationPricingService._pricing_cache = {
            "gpt-image-1:low:1024x1024": Decimal("0.011"),
            "gpt-image-1:medium:1024x1024": Decimal("0.042"),
            "gpt-image-1:high:1536x1024": Decimal("0.250"),
        }
        ImageGenerationPricingService._usd_eur_rate = Decimal("0.85")

    def teardown_method(self) -> None:
        """Clear cache after tests."""
        ImageGenerationPricingService._pricing_cache = {}

    def test_known_pricing_returns_correct_costs(self) -> None:
        """Known model/quality/size returns correct USD and EUR costs."""
        cost_usd, cost_eur, rate = ImageGenerationPricingService.get_cost_per_image(
            "gpt-image-1", "low", "1024x1024"
        )
        assert cost_usd == Decimal("0.011")
        assert cost_eur == Decimal("0.011") * Decimal("0.85")
        assert rate == Decimal("0.85")

    def test_unknown_pricing_returns_zero(self) -> None:
        """Unknown model/quality/size returns zero cost."""
        cost_usd, cost_eur, rate = ImageGenerationPricingService.get_cost_per_image(
            "unknown-model", "low", "1024x1024"
        )
        assert cost_usd == Decimal("0")
        assert cost_eur == Decimal("0")
        assert rate == Decimal("0.85")

    def test_high_quality_large_size(self) -> None:
        """High quality + large size returns higher cost."""
        cost_usd, _, _ = ImageGenerationPricingService.get_cost_per_image(
            "gpt-image-1", "high", "1536x1024"
        )
        assert cost_usd == Decimal("0.250")

    def test_is_cache_loaded(self) -> None:
        """is_cache_loaded returns True when cache has entries."""
        assert ImageGenerationPricingService.is_cache_loaded() is True

    def test_is_cache_loaded_empty(self) -> None:
        """is_cache_loaded returns False when cache is empty."""
        ImageGenerationPricingService._pricing_cache = {}
        assert ImageGenerationPricingService.is_cache_loaded() is False

    def test_get_usd_eur_rate(self) -> None:
        """get_usd_eur_rate returns cached rate."""
        assert ImageGenerationPricingService.get_usd_eur_rate() == Decimal("0.85")


@pytest.mark.unit
class TestLoadPricingCache:
    """Tests for ImageGenerationPricingService.load_pricing_cache()."""

    def teardown_method(self) -> None:
        """Clear cache after tests."""
        ImageGenerationPricingService._pricing_cache = {}

    async def test_load_populates_cache(self) -> None:
        """load_pricing_cache populates the cache from DB entries."""
        mock_entry = MagicMock()
        mock_entry.model = "gpt-image-1"
        mock_entry.quality = "low"
        mock_entry.size = "1024x1024"
        mock_entry.cost_per_image_usd = Decimal("0.011")

        mock_db = AsyncMock()
        with (
            patch(
                "src.domains.image_generation.pricing_service.ImageGenerationPricingRepository"
            ) as mock_repo_cls,
            patch(
                "src.domains.image_generation.pricing_service.CurrencyRateService"
            ) as mock_currency_cls,
        ):
            mock_repo_cls.return_value.get_active_pricing = AsyncMock(return_value=[mock_entry])
            mock_currency_cls.return_value.get_rate = AsyncMock(return_value=Decimal("0.90"))

            await ImageGenerationPricingService.load_pricing_cache(mock_db)

        assert len(ImageGenerationPricingService._pricing_cache) == 1
        assert ImageGenerationPricingService._pricing_cache["gpt-image-1:low:1024x1024"] == Decimal(
            "0.011"
        )
        assert ImageGenerationPricingService._usd_eur_rate == Decimal("0.90")
