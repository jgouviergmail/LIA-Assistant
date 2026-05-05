"""Pydantic schemas for image generation pricing API.

Defines request/response models for the admin image pricing CRUD endpoints.
Mirrors the pattern from src/domains/llm/schemas.py but adapted for
per-image pricing keyed by (model, quality, size).

Phase: evolution — AI Image Generation
Created: 2026-03-26
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Enum-like literal type for the provider field. Must stay in sync with
# LLMProviderEnum (apps/api/src/domains/llm/models.py) AND LLM_PROVIDERS
# (apps/api/src/domains/llm_config/constants.py).
ProviderLiteral = Literal[
    "openai",
    "anthropic",
    "deepseek",
    "perplexity",
    "ollama",
    "gemini",
    "qwen",
]


class ImagePricingResponse(BaseModel):
    """Response model for image generation pricing information.

    Returned by list/create/update endpoints.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: ProviderLiteral
    model: str
    quality: str
    size: str
    cost_per_image_usd: Decimal
    effective_from: datetime
    is_active: bool


class ImagePricingCreate(BaseModel):
    """Request model for creating a new image pricing entry.

    Composite key: (model, quality, size). Must be unique among active entries.
    Application-level invariant: all rows for a given ``model`` must share
    the same ``provider`` (validated at the service layer).
    """

    provider: ProviderLiteral = Field(
        ...,
        description="Provider that hosts this image-generation model",
    )
    model: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Image generation model (e.g., 'gpt-image-1')",
    )
    quality: str = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Quality level (e.g., 'low', 'medium', 'high')",
    )
    size: str = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Image dimensions (e.g., '1024x1024')",
    )
    cost_per_image_usd: Decimal = Field(
        ...,
        gt=0,
        description="Cost per generated image in USD",
    )


class ImagePricingUpdate(BaseModel):
    """Request model for updating image pricing (creates new version, deactivates old).

    ``provider`` is intentionally NOT updatable — it is intrinsic to a model.
    model/quality/size can be changed to rename a pricing entry (uniqueness
    validated server-side).
    """

    model: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="New model name (optional, for renaming)",
    )
    quality: str | None = Field(
        default=None,
        min_length=1,
        max_length=20,
        description="New quality level (optional)",
    )
    size: str | None = Field(
        default=None,
        min_length=1,
        max_length=20,
        description="New size (optional)",
    )
    cost_per_image_usd: Decimal = Field(
        ...,
        gt=0,
        description="Cost per generated image in USD",
    )


class ImagePricingListResponse(BaseModel):
    """Response model for paginated image pricing list."""

    total: int
    page: int
    page_size: int
    total_pages: int
    entries: list[ImagePricingResponse]
