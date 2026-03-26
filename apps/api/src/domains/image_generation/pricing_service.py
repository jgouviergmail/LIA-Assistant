"""Image generation pricing calculation service.

Provides cached pricing lookups and cost calculations for AI image generation.
Pricing data is loaded from the database at startup and cached in memory.

Follows the GoogleApiPricingService pattern exactly:
- Class-level in-memory cache (no Redis lookup at runtime)
- Loaded at startup via load_pricing_cache()
- Cross-worker invalidation via Redis Pub/Sub (ADR-063)
- Synchronous get_cost_per_image() for use in TrackingContext

Phase: evolution — AI Image Generation
Created: 2026-03-25
"""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.image_generation.repository import ImageGenerationPricingRepository
from src.infrastructure.external.currency_api import CurrencyRateService
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class ImageGenerationPricingService:
    """Calculate costs for AI image generation calls.

    Uses in-memory cache for fast lookups during request processing.
    Cache is populated at application startup from the database.

    Class Attributes:
        _pricing_cache: Dict mapping "model:quality:size" to cost_per_image_usd.
        _usd_eur_rate: Cached USD to EUR exchange rate.

    Example:
        >>> cost_usd, cost_eur, rate = ImageGenerationPricingService.get_cost_per_image(
        ...     "gpt-image-1", "medium", "1024x1024"
        ... )
        >>> print(f"Cost: ${cost_usd} = {cost_eur} EUR")
    """

    _pricing_cache: dict[str, Decimal] = {}
    _usd_eur_rate: Decimal = Decimal(str(settings.default_usd_eur_rate))

    @classmethod
    async def load_pricing_cache(cls, db: AsyncSession) -> None:
        """Load pricing from database into memory cache.

        Should be called at application startup (lifespan context).

        Args:
            db: Database session for querying pricing data.
        """
        repo = ImageGenerationPricingRepository(db)
        pricing_entries = await repo.get_active_pricing()

        cls._pricing_cache = {
            f"{p.model}:{p.quality}:{p.size}": p.cost_per_image_usd for p in pricing_entries
        }

        # Fetch current USD/EUR rate
        currency_service = CurrencyRateService()
        try:
            rate = await currency_service.get_rate("USD", "EUR")
            if rate is not None:
                cls._usd_eur_rate = rate
        except Exception as e:
            logger.warning(
                "image_generation_pricing_currency_rate_fallback",
                error=str(e),
                fallback_rate=float(settings.default_usd_eur_rate),
            )
            cls._usd_eur_rate = Decimal(str(settings.default_usd_eur_rate))

        logger.info(
            "image_generation_pricing_loaded",
            entries=len(cls._pricing_cache),
            usd_eur_rate=float(cls._usd_eur_rate),
        )

    @classmethod
    async def invalidate_and_reload(cls, db: AsyncSession) -> None:
        """Reload pricing cache from DB and notify all workers.

        Called by admin endpoint after pricing modifications.
        Publishes cross-worker invalidation via Redis Pub/Sub (ADR-063).

        Args:
            db: Database session for querying pricing data.
        """
        from src.core.constants import CACHE_NAME_IMAGE_GENERATION_PRICING
        from src.infrastructure.cache.invalidation import publish_cache_invalidation

        await cls.load_pricing_cache(db)
        await publish_cache_invalidation(CACHE_NAME_IMAGE_GENERATION_PRICING)

    @classmethod
    def get_cost_per_image(
        cls,
        model: str,
        quality: str,
        size: str,
    ) -> tuple[Decimal, Decimal, Decimal]:
        """Get cost in USD, EUR, and the exchange rate for a single image.

        This is a synchronous method that uses the pre-loaded cache.
        Safe to call from anywhere without database access.

        Args:
            model: Image generation model (e.g., "gpt-image-1").
            quality: Quality level (e.g., "medium").
            size: Image dimensions (e.g., "1024x1024").

        Returns:
            Tuple of (cost_usd, cost_eur, usd_to_eur_rate).
            Returns (0, 0, rate) if pricing not found in cache.
        """
        key = f"{model}:{quality}:{size}"
        cost_usd = cls._pricing_cache.get(key, Decimal("0"))

        if cost_usd == Decimal("0"):
            logger.warning(
                "image_generation_pricing_not_found",
                model=model,
                quality=quality,
                size=size,
                cache_keys=list(cls._pricing_cache.keys()),
            )

        cost_eur = cost_usd * cls._usd_eur_rate

        return cost_usd, cost_eur, cls._usd_eur_rate

    @classmethod
    def get_usd_eur_rate(cls) -> Decimal:
        """Get the current cached USD to EUR exchange rate.

        Returns:
            USD to EUR exchange rate as Decimal.
        """
        return cls._usd_eur_rate

    @classmethod
    def is_cache_loaded(cls) -> bool:
        """Check if pricing cache has been loaded.

        Returns:
            True if cache contains pricing data.
        """
        return len(cls._pricing_cache) > 0
