"""SQLAlchemy models for image generation pricing.

Models:
- ImageGenerationPricing: Per-image pricing by model, quality, and size.

Provider-agnostic: supports any image generation provider (OpenAI, Gemini, etc.)
by keying on model name (globally unique across providers).

Phase: evolution — AI Image Generation
Created: 2026-03-25
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class ImageGenerationPricing(BaseModel):
    """Pricing configuration for image generation models.

    Stores cost per image for each (model, quality, size) combination.
    Supports temporal versioning via effective_from and is_active flags.

    Attributes:
        model: Image generation model identifier (e.g., "gpt-image-1").
        quality: Quality level (e.g., "low", "medium", "high").
        size: Image dimensions (e.g., "1024x1024", "1536x1024").
        cost_per_image_usd: Cost per generated image in USD.
        effective_from: Date when this pricing became effective.
        is_active: Whether this pricing entry is currently active.

    Example:
        gpt-image-1, medium, 1024x1024 → $0.042 per image
    """

    __tablename__ = "image_generation_pricing"

    # Pricing key: (model, quality, size)
    model: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Image generation model (e.g., 'gpt-image-1')",
    )
    quality: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Quality level (e.g., 'low', 'medium', 'high')",
    )
    size: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Image dimensions (e.g., '1024x1024')",
    )

    # Pricing
    cost_per_image_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),
        nullable=False,
        comment="Cost per generated image in USD",
    )

    # Versioning
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="Date from which this pricing is effective",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Whether this pricing entry is currently active",
    )

    __table_args__ = (
        UniqueConstraint(
            "model",
            "quality",
            "size",
            "effective_from",
            name="uq_image_gen_pricing_model_quality_size_effective",
        ),
        Index(
            "ix_image_gen_pricing_active_lookup",
            "model",
            "quality",
            "size",
            "is_active",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ImageGenerationPricing(model={self.model}, "
            f"quality={self.quality}, size={self.size}, "
            f"cost=${self.cost_per_image_usd}, active={self.is_active})>"
        )
