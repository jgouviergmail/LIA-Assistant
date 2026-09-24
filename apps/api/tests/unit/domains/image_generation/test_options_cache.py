"""Unit tests for the options cache: it holds exactly what can run (ADR-305)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.domains.image_generation.families import QWEN_IMAGE_3
from src.domains.image_generation.models import ImageGenerationPricing
from src.domains.image_generation.options_cache import ImageOptionsCache
from src.domains.llm.models import LLMProviderEnum


def _row(provider: str, model: str, quality: str, size: str, cost: str) -> ImageGenerationPricing:
    return ImageGenerationPricing(
        provider=LLMProviderEnum(provider),
        model=model,
        quality=quality,
        size=size,
        cost_per_image_usd=Decimal(cost),
        is_active=True,
    )


_QWEN_SIZES = ("2448x1632", "1024x1536", "2048x2048", "1536x1024", "1632x2448", "1024x1024")


@pytest.mark.unit
class TestBuildByModel:
    """Only a declared family with a client, and only the rows it accepts."""

    def test_a_model_no_family_declares_is_not_offered(self) -> None:
        built = ImageOptionsCache._build_by_model(
            [_row("gemini", "gemini-2.5-flash-image", "standard", "1024x1024", "0.039")]
        )
        assert built == {}

    def test_rows_the_family_refuses_are_dropped(self) -> None:
        built = ImageOptionsCache._build_by_model(
            [
                _row("qwen", "qwen-image-3.0", "standard", "1024x1024", "0.024754"),
                # OpenAI vocabulary on a Qwen model: never offered, never billed.
                _row("qwen", "qwen-image-3.0", "low", "1024x1024", "0.01"),
                # Beyond the documented envelope.
                _row("qwen", "qwen-image-3.0", "standard", "4096x4096", "0.1"),
            ]
        )
        options = built["qwen-image-3.0"]
        assert [q.value for q in options.qualities] == ["standard"]
        assert [s.value for s in options.sizes] == ["1024x1024"]

    def test_a_stale_row_of_another_provider_is_never_offered(self) -> None:
        """The admin write path forbids mixing providers; a leftover must not leak."""
        built = ImageOptionsCache._build_by_model(
            [
                _row("openai", "gpt-image-2", "low", "1024x1024", "0.011"),
                _row("qwen", "gpt-image-2", "low", "1536x1024", "0.2"),
            ]
        )
        options = built["gpt-image-2"]
        assert options.provider == "openai"
        assert [s.value for s in options.sizes] == ["1024x1024"]

    def test_a_model_left_with_no_accepted_row_is_not_offered(self) -> None:
        built = ImageOptionsCache._build_by_model(
            [_row("qwen", "qwen-image-3.0", "high", "1024x1024", "0.1")]
        )
        assert built == {}

    def test_qwen_sizes_carry_orientation_and_tier_in_reading_order(self) -> None:
        built = ImageOptionsCache._build_by_model(
            [_row("qwen", "qwen-image-3.0-pro", "standard", s, "0.03438") for s in _QWEN_SIZES]
        )
        options = built["qwen-image-3.0-pro"]
        assert options.family is QWEN_IMAGE_3 and options.provider == "qwen"
        assert [(s.value, s.orientation, s.tier) for s in options.sizes] == [
            ("1024x1024", "square", "1k"),
            ("1536x1024", "landscape", "1k"),
            ("1024x1536", "portrait", "1k"),
            ("2048x2048", "square", "2k"),
            ("2448x1632", "landscape", "2k"),
            ("1632x2448", "portrait", "2k"),
        ]

    def test_openai_qualities_follow_the_family_order_with_their_price_range(self) -> None:
        rows = [
            _row("openai", "gpt-image-2", quality, size, cost)
            for quality, size, cost in (
                ("high", "1024x1024", "0.167"),
                ("low", "1024x1024", "0.011"),
                ("low", "1024x1536", "0.016"),
                ("medium", "1024x1024", "0.042"),
            )
        ]
        options = ImageOptionsCache._build_by_model(rows)["gpt-image-2"]
        assert [(q.value, q.min_cost_usd, q.max_cost_usd) for q in options.qualities] == [
            ("low", Decimal("0.011"), Decimal("0.016")),
            ("medium", Decimal("0.042"), Decimal("0.042")),
            ("high", Decimal("0.167"), Decimal("0.167")),
        ]
        assert all(s.tier is None for s in options.sizes)
