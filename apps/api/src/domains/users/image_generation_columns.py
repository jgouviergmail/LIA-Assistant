"""How the person wants their images made — the columns of ``users`` they live in.

A declarative mixin like ``TurnPreferencesColumns`` (moved out of ``models.py``,
which is held under the logical-size cap): the opt-in, the preferred quality,
size and output format — intents mapped onto the configured model's offer at run
time (``image_generation/preferences.py``, ADR-305) — and the prompt enhancement
opt-in (ADR-315), off until the person turns it on and inert while the operator
withdraws the capability (``IMAGE_PROMPT_ENHANCEMENT_ENABLED``). All are read by
the image tools and written through the generic profile update. Migration
``79db1056a28e`` added the last one.
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.constants import (
    IMAGE_GENERATION_ENABLED_DEFAULT,
    IMAGE_GENERATION_OUTPUT_FORMAT_DEFAULT,
    IMAGE_GENERATION_PROMPT_ENHANCEMENT_DEFAULT,
    IMAGE_GENERATION_QUALITY_DEFAULT,
    IMAGE_GENERATION_SIZE_DEFAULT,
)


class ImageGenerationColumns:
    """Mapped columns of the image generation preferences (a declarative mixin)."""

    image_generation_enabled: Mapped[bool] = mapped_column(
        default=IMAGE_GENERATION_ENABLED_DEFAULT,
        nullable=False,
        server_default="true",
        comment="User opt-in for AI image generation feature.",
    )
    image_generation_default_quality: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=IMAGE_GENERATION_QUALITY_DEFAULT,
        server_default=IMAGE_GENERATION_QUALITY_DEFAULT,
        comment="Preferred image quality; mapped onto the configured model's offer.",
    )
    image_generation_default_size: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=IMAGE_GENERATION_SIZE_DEFAULT,
        server_default=IMAGE_GENERATION_SIZE_DEFAULT,
        comment="Preferred image size (WIDTHxHEIGHT); mapped onto the model's offer.",
    )
    image_generation_output_format: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default=IMAGE_GENERATION_OUTPUT_FORMAT_DEFAULT,
        server_default=IMAGE_GENERATION_OUTPUT_FORMAT_DEFAULT,
        comment="Default output format: png, jpeg, webp.",
    )
    image_generation_prompt_enhancement: Mapped[bool] = mapped_column(
        default=IMAGE_GENERATION_PROMPT_ENHANCEMENT_DEFAULT,
        nullable=False,
        server_default="false",
        comment=(
            "User opt-in for rewriting image prompts with recognised prompting "
            "techniques before generation (ADR-315)."
        ),
    )


__all__ = ["ImageGenerationColumns"]
