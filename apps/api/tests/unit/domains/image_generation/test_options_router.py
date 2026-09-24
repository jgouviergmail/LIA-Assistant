"""The settings are told what the next image will use (ADR-305)."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.core.exceptions import BaseAPIException
from src.domains.image_generation.families import QWEN_IMAGE_3
from src.domains.image_generation.options_cache import ModelOptions, QualityOption, SizeOption
from src.domains.image_generation.options_router import get_image_generation_options
from src.domains.image_generation.preferences import ImageModelNotServedError

_ACTIVE = "src.domains.image_generation.options_router.active_image_options"


def _qwen() -> ModelOptions:
    return ModelOptions(
        model="qwen-image-3.0-pro",
        provider="qwen",
        family=QWEN_IMAGE_3,
        qualities=(QualityOption("standard", Decimal("0.03438"), Decimal("0.068761")),),
        sizes=(
            SizeOption("1024x1536", "portrait", "1k"),
            SizeOption("1632x2448", "portrait", "2k"),
        ),
    )


@pytest.mark.unit
async def test_publishes_the_offer_and_the_person_effective_choice() -> None:
    person = SimpleNamespace(
        image_generation_default_quality="high", image_generation_default_size="1024x1536"
    )
    with patch(_ACTIVE, return_value=_qwen()):
        response = await get_image_generation_options(user=person)  # type: ignore[arg-type]

    assert (response.active_model, response.provider) == ("qwen-image-3.0-pro", "qwen")
    # An OpenAI quality, stored before the switch, runs as Qwen's one quality.
    assert response.effective_quality == "standard"
    assert response.effective_size == "1024x1536"
    assert [(s.value, s.orientation, s.tier, s.label_key) for s in response.sizes] == [
        ("1024x1536", "portrait", "1k", "settings.image_generation.size_portrait"),
        ("1632x2448", "portrait", "2k", "settings.image_generation.size_portrait"),
    ]


@pytest.mark.unit
async def test_an_unserved_model_is_a_400_naming_it() -> None:
    person = SimpleNamespace(
        image_generation_default_quality="low", image_generation_default_size=None
    )
    with patch(_ACTIVE, side_effect=ImageModelNotServedError("model 'x' is not served")):
        with pytest.raises(BaseAPIException) as raised:
            await get_image_generation_options(user=person)  # type: ignore[arg-type]
    assert raised.value.status_code == 400
    assert "model 'x'" in raised.value.detail
