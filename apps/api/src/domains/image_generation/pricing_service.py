"""Image generation pricing: what one call costs (ADR-305).

Prices are loaded from ``image_generation_pricing`` at startup, reloaded by the
admin routes, and invalidated cross-worker (ADR-063). A call costs its output
images at the row's per-image price PLUS every reference image of an edit at the
row's reference-image price, when the vendor bills them per image.

The EUR figure uses the pricing cache's rate (``get_cached_usd_eur_rate``) — the
one rate every token, voice and live cost reads, refreshed daily and published to
every worker. This service used to fetch a second rate from a currency API at load
time, so an image and the tokens around it were converted at two different rates.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.image_generation.repository import ImageGenerationPricingRepository
from src.infrastructure.cache.pricing_cache import get_cached_usd_eur_rate
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ImagePrice:
    """The prices of one (model, quality, size) key.

    Attributes:
        output_usd: Per generated image.
        input_usd: Per reference image sent to an edit; ``None`` when the vendor
            does not bill reference images per image.
    """

    output_usd: Decimal
    input_usd: Decimal | None


class ImageGenerationPricingService:
    """In-memory image prices, read synchronously by the ``TrackingContext``.

    Class Attributes:
        _pricing_cache: ``"model:quality:size"`` → :class:`ImagePrice`.
    """

    _pricing_cache: dict[str, ImagePrice] = {}

    @staticmethod
    def _key(model: str, quality: str, size: str) -> str:
        return f"{model}:{quality}:{size}"

    @classmethod
    async def load_pricing_cache(cls, db: AsyncSession) -> None:
        """Load the active prices into memory (startup and reload).

        Args:
            db: Database session for querying pricing data.
        """
        entries = await ImageGenerationPricingRepository(db).get_active_pricing()
        cls._pricing_cache = {
            cls._key(entry.model, entry.quality, entry.size): ImagePrice(
                output_usd=entry.cost_per_image_usd,
                input_usd=entry.cost_per_input_image_usd,
            )
            for entry in entries
        }
        logger.info("image_generation_pricing_loaded", entries=len(cls._pricing_cache))

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
    def get_price(cls, model: str, quality: str, size: str) -> ImagePrice | None:
        """The prices of a key, or ``None`` when no active row prices it."""
        return cls._pricing_cache.get(cls._key(model, quality, size))

    @classmethod
    def cost_of_call(
        cls,
        *,
        model: str,
        quality: str,
        size: str,
        image_count: int,
        input_image_count: int,
    ) -> tuple[Decimal, Decimal, Decimal]:
        """What one call costs, in USD and EUR, and the rate used.

        Args:
            model: The model that ran (the configured one).
            quality: The quality it ran at.
            size: The output size.
            image_count: Images produced.
            input_image_count: Reference images sent (an edit's source).

        Returns:
            ``(cost_usd, cost_eur, usd_to_eur_rate)``; zero cost when no active row
            prices the key, which is logged.
        """
        rate = Decimal(str(get_cached_usd_eur_rate()))
        price = cls.get_price(model, quality, size)
        if price is None:
            logger.warning(
                "image_generation_pricing_not_found",
                model=model,
                quality=quality,
                size=size,
                priced_keys=len(cls._pricing_cache),
            )
            return Decimal("0"), Decimal("0"), rate
        cost_usd = price.output_usd * image_count + (price.input_usd or Decimal("0")) * (
            input_image_count
        )
        return cost_usd, cost_usd * rate, rate

    @classmethod
    def is_cache_loaded(cls) -> bool:
        """Whether the cache holds any price."""
        return len(cls._pricing_cache) > 0
