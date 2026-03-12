"""
External API integration for currency exchange rates.

Uses frankfurter.app (free, reliable, BCE source) with 24h cache.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.core.config import settings

logger = structlog.get_logger(__name__)


class CurrencyRateService:
    """
    Fetch live currency exchange rates from external API.

    Features:
    - Source: api.frankfurter.app (European Central Bank data)
    - Cache: 24h TTL (rates update 1x/day around 16:00 CET)
    - Async: httpx.AsyncClient for non-blocking requests
    - Fallback: Returns None on error (caller handles DB fallback)

    Example:
        >>> service = CurrencyRateService()
        >>> rate = await service.get_rate("USD", "EUR")
        >>> print(f"1 USD = {rate} EUR")
        1 USD = 0.95 EUR
    """

    def __init__(self, api_url: str | None = None) -> None:
        """
        Initialize currency rate service.

        Args:
            api_url: API base URL (default: from settings.currency_api_url)
        """
        self.api_url = api_url or settings.currency_api_url
        self._cache: dict[str, tuple[Decimal, datetime]] = {}
        self._cache_ttl = timedelta(hours=settings.currency_cache_ttl_hours)
        self._timeout = settings.currency_api_timeout_seconds

    async def get_rate(self, from_currency: str, to_currency: str) -> Decimal | None:
        """
        Get exchange rate with 24h cache.

        Args:
            from_currency: Source currency (ISO 4217, e.g., "USD")
            to_currency: Target currency (ISO 4217, e.g., "EUR")

        Returns:
            Exchange rate as Decimal, or None if API unavailable

        Example:
            >>> rate = await service.get_rate("USD", "EUR")
            >>> cost_eur = cost_usd * rate
        """
        cache_key = f"{from_currency}_{to_currency}"

        # Check cache (24h TTL)
        if cache_key in self._cache:
            rate, cached_at = self._cache[cache_key]
            age = datetime.now(UTC) - cached_at
            if age < self._cache_ttl:
                logger.debug(
                    "currency_rate_cache_hit",
                    from_currency=from_currency,
                    to_currency=to_currency,
                    cache_age_hours=age.total_seconds() / 3600,
                )
                return rate

        # Fetch from API with retry logic for network resilience
        @retry(
            retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            reraise=True,
        )
        async def _fetch_rate_with_retry() -> tuple[Decimal, dict[str, Any]]:
            """Fetch currency rate with automatic retries for transient failures."""
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    f"{self.api_url}/latest",
                    params={"from": from_currency, "to": to_currency},
                )
                response.raise_for_status()
                data = response.json()
                rate = Decimal(str(data["rates"][to_currency]))
                return rate, data

        try:
            rate, data = await _fetch_rate_with_retry()

            # Cache result
            self._cache[cache_key] = (rate, datetime.now(UTC))

            logger.info(
                "currency_rate_fetched",
                from_currency=from_currency,
                to_currency=to_currency,
                rate=float(rate),
                source="frankfurter_api",
            )

            return rate

        except (
            httpx.HTTPError,  # Base class for all httpx errors (includes RequestError, HTTPStatusError)
            KeyError,
            ValueError,
            InvalidOperation,
        ) as e:
            logger.error(
                "currency_rate_api_failed",
                from_currency=from_currency,
                to_currency=to_currency,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None  # Caller handles fallback to DB
