"""An image preference is validated for its shape, never for one vendor's list (ADR-305).

What a quality or a size may be depends on the model the administrator configured,
and that can change after the preference was stored. The write path therefore
refuses what can never be a quality or a size; the image domain maps the rest.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.domains.users.schemas import UserUpdate


@pytest.mark.unit
class TestImagePreferenceShape:
    """Accepted: any family's vocabulary. Refused: what no family could offer."""

    @pytest.mark.parametrize(
        ("quality", "size"),
        [
            ("low", "1024x1536"),
            ("high", "1536x1024"),
            # Qwen's vocabulary, which the former OpenAI-only list refused.
            ("standard", "2448x1632"),
            ("standard", "2048x2048"),
        ],
    )
    def test_any_family_vocabulary_is_stored(self, quality: str, size: str) -> None:
        update = UserUpdate(
            image_generation_default_quality=quality, image_generation_default_size=size
        )
        assert (update.image_generation_default_quality, update.image_generation_default_size) == (
            quality,
            size,
        )

    @pytest.mark.parametrize("size", ["1024*1024", "big", "0x1024", "1024x", "x1024"])
    def test_a_size_that_is_not_widthxheight_is_refused(self, size: str) -> None:
        with pytest.raises(ValidationError, match="WIDTHxHEIGHT"):
            UserUpdate(image_generation_default_size=size)

    @pytest.mark.parametrize("quality", ["Low", "very high", "", "q" * 21])
    def test_a_quality_that_is_not_a_short_token_is_refused(self, quality: str) -> None:
        with pytest.raises(ValidationError, match="short lowercase token"):
            UserUpdate(image_generation_default_quality=quality)
