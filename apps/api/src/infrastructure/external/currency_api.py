"""
External API integration for currency exchange rates.

Uses frankfurter.dev/v1 (free, reliable, ECB source) with 24h cache.

Cache is class-level (shared across all instances) so that callers creating
short-lived ``CurrencyRateService()`` instances still benefit from previous
lookups.  A negative-result cache prevents repeated retries when the API is
unreachable (e.g. Docker network issues), avoiding ~19 s × N blocking calls
in the response path.

Since ADR-318 a lookup is a QUOTE: the rate and the day the reference rate was
published, because a conversion shown to a person states which day's rate it
used. And a pair the source does not publish is told apart from an outage —
measured on 2026-09-24, an unknown code answers 404 and the same code twice
422, both immediately: such a pair raises :class:`UnsupportedCurrencyError`,
is never retried and never negative-cached, while ``get_rate`` keeps its
billing contract (``None`` on any failure, the caller falls back to the
database).
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from src.core.config import settings

logger = structlog.get_logger(__name__)

# Negative-cache TTL: when the API fails, skip retries for this duration
_NEGATIVE_CACHE_TTL = timedelta(minutes=5)

#: What the source answers for a pair it does not publish (measured 2026-09-24):
#: 404 for an unknown code, 422 for the same code on both sides.
_UNSUPPORTED_PAIR_STATUSES = frozenset({404, 422})


@dataclass(frozen=True)
class CurrencyQuote:
    """One published rate.

    Attributes:
        rate: How many units of the target one unit of the source is worth.
        rate_date: The day the reference rate belongs to, when the source said
            it — a weekend lookup reads Friday's rate, and the answer says so.
    """

    rate: Decimal
    rate_date: date | None


class UnsupportedCurrencyError(ValueError):
    """The source publishes no rate for this pair — the question, not an outage."""


def _is_transient(error: BaseException) -> bool:
    """Retry what may succeed next time: the network, and a server error.

    A 4xx is an answer about the request: asking again gets the same answer.
    """
    if isinstance(error, httpx.RequestError):
        return True
    return isinstance(error, httpx.HTTPStatusError) and error.response.status_code >= 500


def _rate_date(payload: dict[str, Any]) -> date | None:
    raw = payload.get("date")
    if not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


class CurrencyRateService:
    """
    Fetch live currency exchange rates from external API.

    Features:
    - Source: api.frankfurter.dev/v1 (European Central Bank data)
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
    _rate_cache: ClassVar[dict[str, tuple[CurrencyQuote, datetime]]] = {}
    _negative_cache: ClassVar[dict[str, datetime]] = {}
    _currencies_cache: ClassVar[dict[str, tuple[tuple[str, ...], datetime]]] = {}

    @classmethod
    def reset_caches(cls) -> None:
        """Forget every cached answer (tests, and the integration suite's reset)."""
        cls._rate_cache.clear()
        cls._negative_cache.clear()
        cls._currencies_cache.clear()

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
            Exchange rate as Decimal, or None if the API is unavailable or the
            pair is not published

        Example:
            >>> rate = await service.get_rate("USD", "EUR")
            >>> cost_eur = cost_usd * rate
        """
        try:
            quote = await self.get_quote(from_currency, to_currency)
        except UnsupportedCurrencyError:
            return None  # Billing contract: None, and the caller falls back to the DB
        return quote.rate if quote is not None else None

    async def get_quote(self, from_currency: str, to_currency: str) -> CurrencyQuote | None:
        """
        Get the published rate and its day, with 24h cache and negative-result cache.

        Args:
            from_currency: Source currency (ISO 4217, e.g., "USD")
            to_currency: Target currency (ISO 4217, e.g., "EUR")

        Returns:
            The quote, or None when the API is unavailable (negative-cached).

        Raises:
            UnsupportedCurrencyError: The source publishes no rate for this pair.
        """
        cache_key = f"{from_currency}_{to_currency}"
        now = datetime.now(UTC)

        # Check positive cache (24h TTL)
        if cache_key in self._rate_cache:
            quote, cached_at = self._rate_cache[cache_key]
            if now - cached_at < self._cache_ttl:
                logger.debug(
                    "currency_rate_cache_hit",
                    from_currency=from_currency,
                    to_currency=to_currency,
                    cache_age_hours=(now - cached_at).total_seconds() / 3600,
                )
                return quote

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
            retry=retry_if_exception(_is_transient),
            stop=stop_after_attempt(2),
            wait=wait_exponential(multiplier=0.5, min=1, max=3),
            reraise=True,
        )
        async def _fetch_rate_with_retry() -> CurrencyQuote:
            """Fetch currency rate with automatic retries for transient failures."""
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    f"{self.api_url}/latest",
                    params={"from": from_currency, "to": to_currency},
                )
                response.raise_for_status()
                data = response.json()
                return CurrencyQuote(
                    rate=Decimal(str(data["rates"][to_currency])), rate_date=_rate_date(data)
                )

        try:
            quote = await _fetch_rate_with_retry()
        except httpx.HTTPStatusError as e:
            if e.response.status_code in _UNSUPPORTED_PAIR_STATUSES:
                # An answer about the question: never cached as an outage.
                logger.info(
                    "currency_pair_unsupported",
                    from_currency=from_currency,
                    to_currency=to_currency,
                    status_code=e.response.status_code,
                )
                raise UnsupportedCurrencyError(f"{from_currency}->{to_currency}") from e
            self._remember_failure(cache_key, from_currency, to_currency, e, now)
            return None  # Caller handles fallback to DB
        except (
            httpx.HTTPError,
            KeyError,
            ValueError,
            InvalidOperation,
        ) as e:
            self._remember_failure(cache_key, from_currency, to_currency, e, now)
            return None  # Caller handles fallback to DB

        # Cache result (class-level)
        self._rate_cache[cache_key] = (quote, now)

        logger.info(
            "currency_rate_fetched",
            from_currency=from_currency,
            to_currency=to_currency,
            rate=float(quote.rate),
            rate_date=quote.rate_date.isoformat() if quote.rate_date else None,
            source="frankfurter_api",
        )

        return quote

    def _remember_failure(
        self,
        cache_key: str,
        from_currency: str,
        to_currency: str,
        error: Exception,
        now: datetime,
    ) -> None:
        """Negative-cache a failed lookup: this pair is not asked again for a while.

        Args:
            cache_key: The pair's cache key.
            from_currency: Source currency.
            to_currency: Target currency.
            error: What failed.
            now: When it failed.
        """
        self._negative_cache[cache_key] = now

        logger.error(
            "currency_rate_api_failed",
            from_currency=from_currency,
            to_currency=to_currency,
            error=str(error),
            error_type=type(error).__name__,
            negative_cache_ttl_seconds=_NEGATIVE_CACHE_TTL.total_seconds(),
        )

    async def supported_currencies(self) -> tuple[str, ...] | None:
        """The currency codes the source publishes, cached like a rate.

        Read to NAME the alternatives when a pair is refused, so a model that
        guessed a code corrects its call instead of guessing again.

        Returns:
            The codes, sorted; None when the source cannot be read.
        """
        now = datetime.now(UTC)
        cached = self._currencies_cache.get(self.api_url)
        if cached is not None and now - cached[1] < self._cache_ttl:
            return cached[0]
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(f"{self.api_url}/currencies")
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            logger.warning(
                "currency_list_unavailable",
                error=str(error),
                error_type=type(error).__name__,
            )
            return None
        if not isinstance(payload, dict):
            return None
        codes = tuple(sorted(str(code) for code in payload))
        self._currencies_cache[self.api_url] = (codes, now)
        return codes
