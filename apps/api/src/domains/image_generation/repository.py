"""Repository for image generation pricing database operations.

Provides optimized queries for pricing configuration retrieval,
following the GoogleApiPricingRepository pattern.

Phase: evolution — AI Image Generation
Created: 2026-03-25
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.image_generation.models import ImageGenerationPricing
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class ImageGenerationPricingRepository:
    """Repository for ImageGenerationPricing database operations.

    Provides methods to get active pricing entries for cache loading.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            db: Async database session.
        """
        self.db = db

    async def get_active_pricing(self) -> list[ImageGenerationPricing]:
        """Get all active pricing entries.

        Used at startup to populate the pricing cache.

        Returns:
            List of active ImageGenerationPricing entries.

        Raises:
            SQLAlchemyError: On database error.
        """
        try:
            result = await self.db.execute(
                select(ImageGenerationPricing).where(
                    ImageGenerationPricing.is_active == True  # noqa: E712
                )
            )
            entries = list(result.scalars().all())

            logger.debug(
                "image_generation_pricing_fetched",
                count=len(entries),
            )

            return entries

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "image_generation_get_active_pricing_failed",
                error_type=type(e).__name__,
                error=str(e),
            )
            raise
