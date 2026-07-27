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
    IMAGE_GENERATION_RATE_LIMIT_CALLS_DEFAULT,
    IMAGE_GENERATION_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
    IMAGE_GENERATION_TOOL_TIMEOUT_SECONDS_DEFAULT,
    MAX_IMAGE_GENERATION_TOOL_TIMEOUT_SECONDS_DEFAULT,
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

    # ========================================================================
    # Rate Limiting
    # ========================================================================

    image_generation_rate_limit_calls: int = Field(
        default=IMAGE_GENERATION_RATE_LIMIT_CALLS_DEFAULT,
        ge=1,
        le=100,
        description=(
            "Max image tool calls (generate_image, edit_image — tracked "
            "separately per tool) per user per window. Technical anti-runaway "
            "ceiling for a paid external API; complements the usage_limits "
            "cost caps which are per billing cycle and Redis-cached."
        ),
    )

    image_generation_rate_limit_window: int = Field(
        default=IMAGE_GENERATION_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
        ge=10,
        le=3600,
        description="Rate limit window (seconds) for image generation tools.",
    )

    # ========================================================================
    # Tool Execution Timeout
    # ========================================================================

    image_generation_tool_timeout_seconds: float = Field(
        default=IMAGE_GENERATION_TOOL_TIMEOUT_SECONDS_DEFAULT,
        ge=10.0,
        le=600.0,
        description=(
            "Wall-clock FLOOR (seconds) applied by the parallel executor to a "
            "single image-generation tool step. Default 180s. Measured on "
            "gpt-image-2: quality=medium 1024x1536 takes ~47s, quality=high "
            "1024x1536 takes ~138s — the previous 90s default killed every "
            "high-quality render. This floor also protects against the generic "
            "30s tool default being undercut by a planner step. Lower it only "
            "to fail-fast on slow provider regions."
        ),
    )

    max_image_generation_tool_timeout_seconds: float = Field(
        default=MAX_IMAGE_GENERATION_TOOL_TIMEOUT_SECONDS_DEFAULT,
        ge=10.0,
        le=900.0,
        description=(
            "Wall-clock CEILING (seconds) for an image-generation tool step. "
            "Dedicated to the image family, like browser and sub-agent tools "
            "already have: the generic MAX_TOOL_TIMEOUT_SECONDS (120s) sat "
            "BELOW the measured 138s of a high-quality render, so no value of "
            "the floor above could ever make it succeed. Caps whatever timeout "
            "the planner requests."
        ),
    )
