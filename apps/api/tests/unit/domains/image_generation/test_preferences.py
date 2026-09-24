"""Unit tests for the person's preferences mapped onto the configured model (ADR-305)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest

from src.core.constants import IMAGE_GENERATION_LLM_TYPE
from src.domains.image_generation.families import OPENAI_GPT_IMAGE, QWEN_IMAGE_3
from src.domains.image_generation.options_cache import ModelOptions, QualityOption, SizeOption
from src.domains.image_generation.preferences import (
    ImageModelNotServedError,
    active_image_options,
    edit_size,
    effective_quality,
    effective_size,
)
from src.domains.image_generation.sizing import ImageSize
from src.domains.llm_config.constants import LLM_DEFAULTS


def _openai() -> ModelOptions:
    return ModelOptions(
        model="gpt-image-2",
        provider="openai",
        family=OPENAI_GPT_IMAGE,
        qualities=(
            QualityOption("low", Decimal("0.011"), Decimal("0.016")),
            QualityOption("medium", Decimal("0.042"), Decimal("0.063")),
            QualityOption("high", Decimal("0.167"), Decimal("0.25")),
        ),
        sizes=(
            SizeOption("1024x1024", "square", None),
            SizeOption("1536x1024", "landscape", None),
            SizeOption("1024x1536", "portrait", None),
        ),
    )


def _qwen() -> ModelOptions:
    return ModelOptions(
        model="qwen-image-3.0-pro",
        provider="qwen",
        family=QWEN_IMAGE_3,
        qualities=(QualityOption("standard", Decimal("0.03438"), Decimal("0.068761")),),
        sizes=(
            SizeOption("1024x1024", "square", "1k"),
            SizeOption("1536x1024", "landscape", "1k"),
            SizeOption("1024x1536", "portrait", "1k"),
            SizeOption("2048x2048", "square", "2k"),
            SizeOption("2448x1632", "landscape", "2k"),
            SizeOption("1632x2448", "portrait", "2k"),
        ),
    )


@pytest.mark.unit
class TestEffectiveQuality:
    """A stored quality the model does not offer never costs more than intended."""

    def test_an_offered_quality_is_kept(self) -> None:
        assert effective_quality("high", _openai()) == "high"

    def test_an_unoffered_quality_becomes_the_cheapest_offered(self) -> None:
        options = _openai()
        assert effective_quality("standard", options) == "low"
        assert effective_quality(None, options) == "low"

    def test_switching_to_qwen_maps_any_openai_quality_to_its_one_quality(self) -> None:
        for stored in ("low", "medium", "high"):
            assert effective_quality(stored, _qwen()) == "standard"


@pytest.mark.unit
class TestEffectiveSize:
    """A stored size keeps what the person chose it for: its orientation."""

    def test_an_offered_size_is_kept(self) -> None:
        assert effective_size("2448x1632", _qwen()) == "2448x1632"

    def test_the_1k_sizes_survive_a_switch_between_vendors(self) -> None:
        for stored in ("1024x1024", "1536x1024", "1024x1536"):
            assert effective_size(stored, _qwen()) == stored
            assert effective_size(stored, _openai()) == stored

    def test_a_2k_size_back_on_openai_keeps_its_orientation(self) -> None:
        assert effective_size("1632x2448", _openai()) == "1024x1536"
        assert effective_size("2448x1632", _openai()) == "1536x1024"
        assert effective_size("2048x2048", _openai()) == "1024x1024"

    def test_a_missing_or_malformed_size_uses_the_default_intent(self) -> None:
        # IMAGE_GENERATION_SIZE_DEFAULT is a portrait.
        assert effective_size(None, _qwen()) == "1024x1536"
        assert effective_size("big", _qwen()) == "1024x1536"


@pytest.mark.unit
class TestEditSize:
    """An edit keeps the source's proportions, within the preferred tier."""

    def test_follows_the_source_proportions(self) -> None:
        assert edit_size(ImageSize(4000, 3000), "1024x1536", _openai()) == "1536x1024"
        assert edit_size(ImageSize(3000, 4000), "1024x1024", _openai()) == "1024x1536"

    def test_stays_within_the_tier_the_person_prefers(self) -> None:
        photo = ImageSize(4000, 3000)
        assert edit_size(photo, "1024x1536", _qwen()) == "1536x1024"
        assert edit_size(photo, "1632x2448", _qwen()) == "2448x1632"


@pytest.mark.unit
class TestActiveImageOptions:
    """The configured model is served, or the reason is named."""

    def test_returns_the_configured_model_offer(self) -> None:
        options = _qwen()
        with (
            patch(
                "src.domains.llm_config.cache.LLMConfigOverrideCache.get_override",
                return_value={"provider": "qwen", "model": "qwen-image-3.0-pro"},
            ),
            patch(
                "src.domains.image_generation.preferences.ImageOptionsCache.get_options_for_model",
                return_value=options,
            ) as lookup,
        ):
            assert active_image_options() is options
        lookup.assert_called_once_with("qwen-image-3.0-pro")

    def test_without_an_override_the_slot_default_is_asked_for(self) -> None:
        with (
            patch(
                "src.domains.llm_config.cache.LLMConfigOverrideCache.get_override",
                return_value=None,
            ),
            patch(
                "src.domains.image_generation.preferences.ImageOptionsCache.get_options_for_model",
                return_value=_openai(),
            ) as lookup,
        ):
            active_image_options()
        lookup.assert_called_once_with(LLM_DEFAULTS[IMAGE_GENERATION_LLM_TYPE].model)

    def test_an_unserved_model_is_named(self) -> None:
        with (
            patch(
                "src.domains.llm_config.cache.LLMConfigOverrideCache.get_override",
                return_value={"provider": "gemini", "model": "gemini-2.5-flash-image"},
            ),
            patch(
                "src.domains.image_generation.preferences.ImageOptionsCache.get_options_for_model",
                return_value=None,
            ),
        ):
            with pytest.raises(ImageModelNotServedError, match="gemini-2.5-flash-image"):
                active_image_options()
