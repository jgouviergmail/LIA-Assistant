"""
External API integration for currency exchange rates.

Uses frankfurter.app (free, reliable, BCE source) with 24h cache.

Cache is class-level (shared across all instances) so that callers creating
short-lived ``CurrencyRateService()`` instances still benefit from previous
lookups.  A negative-result cache prevents repeated retries when the API is
unreachable (e.g. Docker network issues), avoiding ~19 s × N blocking calls
in the response path.
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

# Negative-cache TTL: when the API fails, skip retries for this duration
_NEGATIVE_CACHE_TTL = timedelta(minutes=5)


class CurrencyRateService:
    """
    Fetch live currency exchange rates from external API.

    Features:
    - Source: api.frankfurter.app (European Central Bank data)
    - Cache: class-level, 24h TTL (rates update 1x/day around 16:00 CET)
    - Negative cache: 5 min TTL when API is unreachable (avoids retry storms)
    - Async: httpx.AsyncClient for non-blocking requests
    - Fallback: Returns None on error (caller handles DB fallback)

    Example:
        >>> service = CurrencyRateService()
        >>> rate = await service.get_rate("USD", "EUR")
        >>> print(f"1 USD = {rate} EUR")
        1 USD = 0.95 EUR
    """

    # Class-level caches shared across all instances
    _rate_cache: dict[str, tuple[Decimal, datetime]] = {}
    _negative_cache: dict[str, datetime] = {}

    def __init__(self, api_url: str | None = None) -> None:
        """
        Initialize currency rate service.

        Args:
            api_url: API base URL (default: from settings.currency_api_url)
        """
        self.api_url = api_url or settings.currency_api_url
        self._cache_ttl = timedelta(hours=settings.currency_cache_ttl_hours)
        self._timeout = settings.currency_api_timeout_seconds

    async def get_rate(self, from_currency: str, to_currency: str) -> Decimal | None:
        """
        Get exchange rate with 24h cache and negative-result cache.

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
        now = datetime.now(UTC)

        # Check positive cache (24h TTL)
        if cache_key in self._rate_cache:
            rate, cached_at = self._rate_cache[cache_key]
            if now - cached_at < self._cache_ttl:
                logger.debug(
                    "currency_rate_cache_hit",
                    from_currency=from_currency,
                    to_currency=to_currency,
                    cache_age_hours=(now - cached_at).total_seconds() / 3600,
                )
                return rate

        # Check negative cache — skip API entirely if it failed recently
        if cache_key in self._negative_cache:
            neg_ts = self._negative_cache[cache_key]
            if now - neg_ts < _NEGATIVE_CACHE_TTL:
                logger.debug(
                    "currency_rate_negative_cache_hit",
                    from_currency=from_currency,
                    to_currency=to_currency,
                    retry_in_seconds=(_NEGATIVE_CACHE_TTL - (now - neg_ts)).total_seconds(),
                )
                return None
            # Expired — remove and retry
            del self._negative_cache[cache_key]

        # Fetch from API with retry logic for network resilience
        @retry(
            retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
            stop=stop_after_attempt(2),
            wait=wait_exponential(multiplier=0.5, min=1, max=3),
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

            # Cache result (class-level)
            self._rate_cache[cache_key] = (rate, now)

            logger.info(
                "currency_rate_fetched",
                from_currency=from_currency,
                to_currency=to_currency,
                rate=float(rate),
                source="frankfurter_api",
            )

            return rate

        except (
            httpx.HTTPError,
            KeyError,
            ValueError,
            InvalidOperation,
        ) as e:
            # Negative cache: don't retry this pair for _NEGATIVE_CACHE_TTL
            self._negative_cache[cache_key] = now

            logger.error(
                "currency_rate_api_failed",
                from_currency=from_currency,
                to_currency=to_currency,
                error=str(e),
                error_type=type(e).__name__,
                negative_cache_ttl_seconds=_NEGATIVE_CACHE_TTL.total_seconds(),
            )
            return None  # Caller handles fallback to DB
