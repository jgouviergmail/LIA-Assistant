"""
Google API pricing calculation service.

Provides cached pricing lookups and cost calculations for Google Maps Platform APIs.
Pricing data is loaded from the database at startup and cached in memory.

Author: Claude Code (Opus 4.5)
Date: 2026-02-04
"""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.google_api.repository import GoogleApiPricingRepository
from src.infrastructure.external.currency_api import CurrencyRateService
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class GoogleApiPricingService:
    """
    Calculate costs for Google API calls.

    Uses in-memory cache for fast lookups during request processing.
    Cache is populated at application startup from the database.

    Class Attributes:
        _pricing_cache: Dict mapping "api_name:endpoint" to cost_per_1000_usd
        _usd_eur_rate: Cached USD to EUR exchange rate

    Example:
        >>> cost_usd, cost_eur, rate = GoogleApiPricingService.get_cost_per_request("places", "/places:searchText")
        >>> print(f"Cost: ${cost_usd} = {cost_eur} EUR")
    """

    _pricing_cache: dict[str, Decimal] = {}
    _usd_eur_rate: Decimal = Decimal(str(settings.default_usd_eur_rate))

    @classmethod
    async def load_pricing_cache(cls, db: AsyncSession) -> None:
        """
        Load pricing from database into memory cache.

        Should be called at application startup (lifespan context).

        Args:
            db: Database session for querying pricing data.
        """
        repo = GoogleApiPricingRepository(db)
        pricing_entries = await repo.get_active_pricing()

        cls._pricing_cache = {
            f"{p.api_name}:{p.endpoint}": p.cost_per_1000_usd for p in pricing_entries
        }

        # Fetch current USD/EUR rate
        currency_service = CurrencyRateService()
        try:
            rate = await currency_service.get_rate("USD", "EUR")
            if rate is not None:
                cls._usd_eur_rate = rate
        except Exception as e:
            logger.warning(
                "google_api_pricing_currency_rate_fallback",
                error=str(e),
                fallback_rate=float(settings.default_usd_eur_rate),
            )
            cls._usd_eur_rate = Decimal(str(settings.default_usd_eur_rate))

        logger.info(
            "google_api_pricing_loaded",
            entries=len(cls._pricing_cache),
            usd_eur_rate=float(cls._usd_eur_rate),
        )

    @classmethod
    def get_cost_per_request(
        cls,
        api_name: str,
        endpoint: str,
    ) -> tuple[Decimal, Decimal, Decimal]:
        """
        Get cost in USD, EUR, and the exchange rate used for a single request.

        This is a synchronous method that uses the pre-loaded cache.
        Safe to call from anywhere without database access.

        Args:
            api_name: API identifier (places, routes, geocoding, static_maps)
            endpoint: Endpoint path (e.g., /places:searchText)

        Returns:
            Tuple of (cost_usd, cost_eur, usd_to_eur_rate)
            Returns (0, 0, rate) if pricing not found in cache.
        """
        key = f"{api_name}:{endpoint}"
        cost_per_1000 = cls._pricing_cache.get(key, Decimal("0"))

        if cost_per_1000 == Decimal("0"):
            logger.warning(
                "google_api_pricing_not_found",
                api_name=api_name,
                endpoint=endpoint,
                cache_keys=list(cls._pricing_cache.keys()),
            )

        cost_usd = cost_per_1000 / Decimal("1000")
        cost_eur = cost_usd * cls._usd_eur_rate

        return cost_usd, cost_eur, cls._usd_eur_rate

    @classmethod
    def get_usd_eur_rate(cls) -> Decimal:
        """
        Get the current cached USD to EUR exchange rate.

        Returns:
            USD to EUR exchange rate as Decimal.
        """
        return cls._usd_eur_rate

    @classmethod
    def is_cache_loaded(cls) -> bool:
        """
        Check if pricing cache has been loaded.

        Returns:
            True if cache contains pricing data.
        """
        return len(cls._pricing_cache) > 0
