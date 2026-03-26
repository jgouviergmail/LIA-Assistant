"""
Image generation configuration module.

Contains settings for the AI image generation feature:
- Feature toggle (image_generation_enabled)
- Max images per request
- Default output format

Note: The model (e.g., gpt-image-1) is managed via the admin LLM Config system
(LLM_TYPES_REGISTRY / LLMConfigOverrideCache), not via these settings.
Per-user preferences (quality, size, format) are stored on the User model.

Phase: evolution — AI Image Generation
Created: 2026-03-25
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    IMAGE_GENERATION_ENABLED_DEFAULT,
    IMAGE_GENERATION_MAX_IMAGES_DEFAULT,
)


class ImageGenerationSettings(BaseSettings):
    """Settings for the AI image generation feature."""

    # ========================================================================
    # Feature Toggle
    # ========================================================================

    image_generation_enabled: bool = Field(
        default=IMAGE_GENERATION_ENABLED_DEFAULT,
        description=(
            "Global feature flag for AI image generation. "
            "When false, the generate_image tool is not registered and the "
            "image_generation domain is not available in the planner catalogue."
        ),
    )

    # ========================================================================
    # Generation Constraints
    # ========================================================================

    image_generation_max_images_per_request: int = Field(
        default=IMAGE_GENERATION_MAX_IMAGES_DEFAULT,
        ge=1,
        le=4,
        description=(
            "Maximum number of images a single tool call can generate. "
            "Higher values increase cost proportionally."
        ),
    )
