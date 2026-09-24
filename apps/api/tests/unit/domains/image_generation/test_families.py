"""Unit tests for the image families: what each model accepts and how it bills (ADR-305)."""

from __future__ import annotations

import pytest

from src.domains.image_generation.families import (
    OPENAI_GPT_IMAGE,
    QWEN_IMAGE_3,
    resolve_image_family,
)
from src.domains.image_generation.sizing import ImageSize


@pytest.mark.unit
class TestResolveImageFamily:
    """A family is found by provider AND model; nothing else is servable."""

    @pytest.mark.parametrize(
        "model", ["gpt-image-1", "gpt-image-1-mini", "gpt-image-1.5", "gpt-image-2"]
    )
    def test_openai_gpt_image_models(self, model: str) -> None:
        assert resolve_image_family("openai", model) is OPENAI_GPT_IMAGE

    @pytest.mark.parametrize("model", ["qwen-image-3.0", "qwen-image-3.0-pro"])
    def test_qwen_image_3_models(self, model: str) -> None:
        assert resolve_image_family("qwen", model) is QWEN_IMAGE_3

    @pytest.mark.parametrize(
        ("provider", "model"),
        [
            # Another vendor's image model: no client serves it.
            ("gemini", "gemini-2.5-flash-image"),
            # A Qwen image model on another API shape (async DashScope, other params).
            ("qwen", "qwen-image-plus"),
            # The right name under the wrong provider is not the same model.
            ("qwen", "gpt-image-2"),
            ("openai", "qwen-image-3.0-pro"),
            # A chat model.
            ("openai", "gpt-6-sol"),
        ],
    )
    def test_anything_else_is_not_servable(self, provider: str, model: str) -> None:
        assert resolve_image_family(provider, model) is None


@pytest.mark.unit
class TestOpenAIFamily:
    """OpenAI prices three sizes per image and bills an edit's input as tokens."""

    def test_accepts_its_priced_vocabulary(self) -> None:
        for quality in ("low", "medium", "high"):
            for size in ("1024x1024", "1536x1024", "1024x1536"):
                assert OPENAI_GPT_IMAGE.refusal(quality, size) is None

    def test_refuses_another_vendor_vocabulary_and_says_what_it_accepts(self) -> None:
        refusal = OPENAI_GPT_IMAGE.refusal("standard", "1024x1024")
        assert refusal is not None and "low, medium, high" in refusal
        refusal = OPENAI_GPT_IMAGE.refusal("low", "2048x2048")
        assert refusal is not None and "1024x1536" in refusal

    def test_has_no_billing_tier(self) -> None:
        assert OPENAI_GPT_IMAGE.tier_of(ImageSize(1024, 1024)) is None

    def test_does_not_bill_reference_images_per_image(self) -> None:
        assert OPENAI_GPT_IMAGE.bills_reference_images_per_image is False

    def test_fits_the_source_within_the_output(self) -> None:
        """OpenAI bills an input image by its tokens, which grow with its area."""
        output = ImageSize(1536, 1024)
        assert OPENAI_GPT_IMAGE.source_box(output) == output


@pytest.mark.unit
class TestQwenFamily:
    """Qwen accepts an area envelope and bills by an output-area tier."""

    @pytest.mark.parametrize(
        "size", ["1024x1024", "1536x1024", "1024x1536", "2048x2048", "2448x1632", "1632x2448"]
    )
    def test_accepts_the_six_offered_sizes(self, size: str) -> None:
        assert QWEN_IMAGE_3.refusal("standard", size) is None

    @pytest.mark.parametrize(
        ("size", "why"),
        [
            ("511x511", "area below 512x512"),
            ("2049x2049", "area above 2048x2048"),
            ("4096x480", "aspect beyond 8:1"),
        ],
    )
    def test_refuses_outside_the_documented_envelope(self, size: str, why: str) -> None:
        assert QWEN_IMAGE_3.refusal("standard", size) is not None, why

    def test_offers_one_quality(self) -> None:
        assert QWEN_IMAGE_3.qualities == ("standard",)
        assert QWEN_IMAGE_3.refusal("low", "1024x1024") is not None

    def test_refuses_a_malformed_size(self) -> None:
        assert QWEN_IMAGE_3.refusal("standard", "1024*1024") is not None

    @pytest.mark.parametrize(
        ("size", "tier"),
        [
            ("1024x1024", "1k"),
            ("1536x1024", "1k"),
            # The vendor's threshold is inclusive: area <= 2,250,000 is 1K.
            ("1500x1500", "1k"),
            ("1501x1500", "2k"),
            ("2048x2048", "2k"),
            ("2448x1632", "2k"),
        ],
    )
    def test_tier_follows_the_vendor_threshold(self, size: str, tier: str) -> None:
        assert QWEN_IMAGE_3.tier_of(ImageSize.parse(size)) == tier

    def test_bills_reference_images_per_image(self) -> None:
        assert QWEN_IMAGE_3.bills_reference_images_per_image is True

    def test_keeps_as_much_of_the_source_as_the_model_reads(self) -> None:
        """The vendor documents 2048 px per edge as its input ceiling, whatever the output."""
        assert QWEN_IMAGE_3.source_box(ImageSize(1024, 1024)) == ImageSize(2048, 2048)
        assert QWEN_IMAGE_3.source_max_bytes == 10 * 1024 * 1024


@pytest.mark.unit
class TestPricingRefusal:
    """A pricing row states the reference-image price its vendor bills — no more, no less."""

    def test_qwen_requires_the_reference_image_price(self) -> None:
        refusal = QWEN_IMAGE_3.pricing_refusal("standard", "1024x1024", has_input_price=False)
        assert refusal is not None and "required" in refusal
        assert QWEN_IMAGE_3.pricing_refusal("standard", "1024x1024", has_input_price=True) is None

    def test_openai_refuses_a_reference_image_price(self) -> None:
        refusal = OPENAI_GPT_IMAGE.pricing_refusal("low", "1024x1024", has_input_price=True)
        assert refusal is not None and "must be empty" in refusal
        assert OPENAI_GPT_IMAGE.pricing_refusal("low", "1024x1024", has_input_price=False) is None

    def test_the_vocabulary_is_checked_first(self) -> None:
        refusal = QWEN_IMAGE_3.pricing_refusal("low", "1024x1024", has_input_price=True)
        assert refusal is not None and "Quality 'low'" in refusal
