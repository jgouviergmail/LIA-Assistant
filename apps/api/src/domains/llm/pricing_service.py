"""
LLM Pricing Service with caching for cost estimation.

This module provides async-only pricing service for LLM cost calculation.
All pricing operations are asynchronous to support FastAPI async routes.
"""

import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, NamedTuple

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import SUPPORTED_CURRENCIES
from src.core.llm_utils import normalize_model_name
from src.domains.llm.models import CurrencyExchangeRate, LLMModelPricing
from src.domains.llm.pricing_time_slots import find_active_slot

logger = structlog.get_logger(__name__)

# LLM pricing is always in USD (industry standard), with optional conversion to EUR
# These constants are extracted from SUPPORTED_CURRENCIES to ensure type safety
_CURRENCY_USD = SUPPORTED_CURRENCIES[0]  # "USD"
_CURRENCY_EUR = SUPPORTED_CURRENCIES[1]  # "EUR"


class ModelPrice(NamedTuple):
    """
    Container for LLM model pricing information.

    The semantic of the unit prices is given by ``pricing_unit``:
    - ``per_1m_tokens``: price per 1 million tokens (LLM chat/text). Default.
    - ``per_audio_minute`` / ``per_audio_hour``: price per audio duration
      (STT/TTS). Token-based callers (``calculate_token_cost``) early-exit
      with cost = 0 in this case; audio-based costing goes through
      :func:`infrastructure.cache.pricing_cache.get_cached_cost_audio_usd_eur`.

    Attributes:
        model_name: LLM model identifier
        input_price: Input unit price (USD)
        cached_input_price: Cached input unit price (USD), None if not supported
        output_price: Output unit price (USD)
        pricing_unit: Billing unit semantics (per_1m_tokens / per_audio_minute / per_audio_hour)
        effective_from: Date when this pricing became effective
        time_slots: Optional UTC windowed tariff (ADR-223); None = flat pricing
    """

    model_name: str
    input_price: Decimal
    cached_input_price: Decimal | None
    output_price: Decimal
    pricing_unit: str
    effective_from: datetime
    time_slots: list[dict[str, Any]] | None = None


def _token_cost_usd(
    pricing: ModelPrice,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int,
    at: datetime,
) -> float:
    """Per-million USD arithmetic shared by both cost calculators (ADR-223).

    Resolves the active time slot for ``at`` (if the row carries a windowed
    tariff) and prices the three token buckets additively. A slot overrides
    all three unit prices; its ``cached_input_unit_price`` may be None with
    the same semantic as the base column (no separate cache billing).

    Args:
        pricing: The pricing row to apply (``pricing_unit`` already checked
            by the caller to be ``per_1m_tokens``).
        input_tokens: Non-cached input tokens.
        output_tokens: Output tokens.
        cached_tokens: Cached input tokens.
        at: Billing instant (timezone-aware) used for slot resolution.

    Returns:
        Total cost in USD.
    """
    slot = find_active_slot(pricing.time_slots, at)
    if slot is not None:
        input_price = float(slot["input_unit_price"])
        raw_cached = slot.get("cached_input_unit_price")
        cached_price = float(raw_cached) if raw_cached is not None else None
        output_price = float(slot["output_unit_price"])
    else:
        input_price = float(pricing.input_price)
        cached_price = (
            float(pricing.cached_input_price) if pricing.cached_input_price is not None else None
        )
        output_price = float(pricing.output_price)

    input_cost_usd = (input_tokens / 1_000_000) * input_price
    if cached_price is not None and cached_tokens > 0:
        cached_cost_usd = (cached_tokens / 1_000_000) * cached_price
    else:
        cached_cost_usd = 0.0
    output_cost_usd = (output_tokens / 1_000_000) * output_price

    return input_cost_usd + cached_cost_usd + output_cost_usd


# ============================================================================
# ASYNC PRICING SERVICE
# ============================================================================


class AsyncPricingService:
    """
    Async service for retrieving LLM pricing and currency rates with caching.

    Similar to PricingService but uses async SQLAlchemy for non-blocking queries.
    Uses LRU cache to minimize database queries. Cache expires after TTL.

    Example:
        >>> async with AsyncSessionLocal() as db:
        ...     service = AsyncPricingService(db)
        ...     price = await service.get_active_model_price("gpt-4.1-mini")
        ...     print(f"Input: ${price.input_price}/1M")
    """

    def __init__(self, db: AsyncSession, cache_ttl_seconds: int = 3600) -> None:
        """
        Initialize AsyncPricingService.

        Args:
            db: SQLAlchemy async database session
            cache_ttl_seconds: Cache time-to-live in seconds (default: 1 hour)
        """
        self.db = db
        self.cache_ttl = cache_ttl_seconds
        self._cache_timestamp: dict[str, float] = {}
        self._model_price_cache: dict[str, ModelPrice] = {}
        self._currency_rate_cache: dict[str, Decimal] = {}

    async def get_active_model_price(self, model_name: str) -> ModelPrice | None:
        """
        Get active pricing for a specific LLM model (async).

        Queries database for active pricing entry. Results are cached for TTL duration.

        Args:
            model_name: LLM model identifier (e.g., "gpt-4.1-mini", "o1-mini")

        Returns:
            ModelPrice if found, None if model pricing not configured

        Example:
            >>> price = await service.get_active_model_price("gpt-4.1-mini")
            >>> if price:
            ...     print(f"${price.input_price}/1M tokens")
        """
        cache_key = f"async_model_price_{model_name}"

        # Check if cache entry exists and is still valid
        if cache_key in self._cache_timestamp:
            age = time.time() - self._cache_timestamp[cache_key]
            if age > self.cache_ttl:
                # Cache expired, invalidate
                self._invalidate_cache(cache_key)
                logger.debug(
                    "model_price_cache_expired",
                    model_name=model_name,
                    cache_age_seconds=age,
                )
            elif cache_key in self._model_price_cache:
                # Cache hit within TTL
                logger.debug(
                    "model_price_cache_hit",
                    model_name=model_name,
                    cache_age_seconds=age,
                )
                return self._model_price_cache[cache_key]

        # Cache miss or expired - query database
        pricing = await self._query_model_pricing(model_name)

        # Store in cache
        if pricing:
            self._model_price_cache[cache_key] = pricing
            self._cache_timestamp[cache_key] = time.time()

        return pricing

    async def _query_model_pricing(self, model_name: str) -> ModelPrice | None:
        """
        Internal method for querying model pricing from database (async).

        Do not call directly, use get_active_model_price() instead.
        Cache is managed by the public method.
        """
        from sqlalchemy.orm import selectinload

        from src.domains.llm.models import LLMModel

        # A model is billed under its EXACT catalogue name when that name owns a
        # tariff, and only otherwise under its normalised name (a dated version
        # inheriting its base model's price). Reading the normalised name alone
        # shadowed explicit per-version tariffs: measured in production,
        # gpt-4o-2024-05-13 owns 5.00/15.00 but was billed gpt-4o's 2.50/10.00.
        # Both candidates are fetched in one query and ordered exact-name-first;
        # the secondary ordering keeps the read deterministic on a database
        # predating the partial unique index (migration 6e7f8a9b0c1d).
        normalized_model = normalize_model_name(model_name)

        stmt = (
            select(LLMModelPricing)
            .join(LLMModelPricing.model)
            .where(
                LLMModel.model_name.in_({model_name, normalized_model}),
                LLMModelPricing.is_active,
            )
            .options(selectinload(LLMModelPricing.model))
            .order_by(
                (LLMModel.model_name == model_name).desc(),
                LLMModelPricing.effective_from.desc(),
                LLMModelPricing.id.desc(),
            )
        )

        result = await self.db.scalars(stmt)
        pricing = result.first()

        if not pricing:
            logger.warning(
                "model_pricing_not_found",
                model_name=model_name,
                fallback_behavior="returning_none",
            )
            return None

        logger.debug(
            "model_pricing_retrieved",
            model_name=model_name,
            input_price=float(pricing.input_unit_price),
            output_price=float(pricing.output_unit_price),
            pricing_unit=pricing.pricing_unit.value,
            cached_input_supported=pricing.cached_input_unit_price is not None,
        )

        return ModelPrice(
            model_name=pricing.model.model_name,
            input_price=pricing.input_unit_price,
            cached_input_price=pricing.cached_input_unit_price,
            output_price=pricing.output_unit_price,
            pricing_unit=pricing.pricing_unit.value,
            effective_from=pricing.effective_from,
            time_slots=pricing.time_slots,
        )

    async def get_active_currency_rate(self, from_currency: str, to_currency: str) -> Decimal:
        """
        Get active exchange rate between two currencies (async).

        Queries database for active currency rate. Results are cached for TTL duration.

        Args:
            from_currency: Source currency code (e.g., "USD")
            to_currency: Target currency code (e.g., "EUR")

        Returns:
            Exchange rate as Decimal (1 from_currency = rate to_currency)

        Raises:
            ValueError: If currency rate not found in database

        Example:
            >>> rate = await service.get_active_currency_rate("USD", "EUR")
            >>> print(f"1 USD = {rate} EUR")
        """
        cache_key = f"async_currency_rate_{from_currency}_{to_currency}"

        # Check cache expiry
        if cache_key in self._cache_timestamp:
            age = time.time() - self._cache_timestamp[cache_key]
            if age > self.cache_ttl:
                self._invalidate_cache(cache_key)
                logger.debug(
                    "currency_rate_cache_expired",
                    from_currency=from_currency,
                    to_currency=to_currency,
                    cache_age_seconds=age,
                )

        # Query with caching
        return await self._get_currency_rate_cached(from_currency, to_currency)

    async def _get_currency_rate_cached(self, from_currency: str, to_currency: str) -> Decimal:
        """
        Internal cached method for querying currency rates (async).

        Manual caching is used instead of @lru_cache (incompatible with async).
        Do not call directly, use get_active_currency_rate() instead.

        The value is stored on a miss and returned on a hit — which the previous
        version did not do: it stamped the timestamp, then queried
        unconditionally and dropped the result, so ``_currency_rate_cache`` was
        written by nobody and only ever cleared. Every cost computation (one per
        LLM call) therefore issued a SELECT, behind a name, a docstring and an
        invalidation path that all described a cache. Expiry stays the caller's
        job: :meth:`get_active_currency_rate` invalidates before delegating.
        """
        cache_key = f"async_currency_rate_{from_currency}_{to_currency}"

        cached = self._currency_rate_cache.get(cache_key)
        if cached is not None:
            logger.debug(
                "currency_rate_cache_hit",
                from_currency=from_currency,
                to_currency=to_currency,
            )
            return cached

        # Deterministic order: most recent first. The partial unique index added
        # by migration 6e7f8a9b0c1d makes duplicate active rates impossible, but
        # a rolling deploy reaches this code before the migration runs.
        stmt = (
            select(CurrencyExchangeRate)
            .where(
                CurrencyExchangeRate.from_currency == from_currency,
                CurrencyExchangeRate.to_currency == to_currency,
                CurrencyExchangeRate.is_active,
            )
            .order_by(
                CurrencyExchangeRate.effective_from.desc(),
                CurrencyExchangeRate.id.desc(),
            )
        )

        result = await self.db.scalars(stmt)
        rate = result.first()

        if not rate:
            # No rate found - raise ValueError as documented
            # Callers should handle this exception and implement their own fallback strategy
            logger.error(
                "currency_rate_not_found",
                from_currency=from_currency,
                to_currency=to_currency,
                remediation="Run currency sync: python -m src.infrastructure.scheduler.currency_sync",
            )
            raise ValueError(f"Currency rate not found: {from_currency}/{to_currency}")

        # Store on the miss only: a failed lookup raises above, so nothing is
        # cached for a pair that has no rate — the next call retries instead of
        # inheriting a stale "known missing" entry.
        self._currency_rate_cache[cache_key] = rate.rate
        self._cache_timestamp[cache_key] = time.time()

        logger.debug(
            "currency_rate_retrieved",
            from_currency=from_currency,
            to_currency=to_currency,
            rate=float(rate.rate),
        )

        return rate.rate

    async def get_model_price_at_date(
        self, model_name: str, at_date: datetime
    ) -> ModelPrice | None:
        """
        Get pricing for a specific LLM model at a given historical date.

        Queries database for pricing entry effective at the specified date.
        Uses effective_from to find the pricing that was active at that time.

        Args:
            model_name: LLM model identifier (e.g., "gpt-4.1-mini", "o1-mini")
            at_date: Date/time for which to retrieve pricing

        Returns:
            ModelPrice if found, None if model pricing not configured for that date

        Example:
            >>> price = await service.get_model_price_at_date("gpt-4.1-mini", datetime(2024, 1, 15))
            >>> if price:
            ...     print(f"${price.input_price}/1M tokens (effective {price.effective_from})")
        """
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from src.domains.llm.models import LLMModel, LLMModelPricing

        # Normalize model name to remove date suffix (e.g., gpt-4.1-mini-2025-04-14 -> gpt-4.1-mini)
        normalized_model = normalize_model_name(model_name)

        # Query for pricing effective at or before the given date
        # Order by effective_from DESC to get the most recent applicable price
        stmt = (
            select(LLMModelPricing)
            .join(LLMModelPricing.model)
            .where(
                LLMModel.model_name == normalized_model,
                LLMModelPricing.effective_from <= at_date,
            )
            .options(selectinload(LLMModelPricing.model))
            .order_by(LLMModelPricing.effective_from.desc())
            .limit(1)
        )

        result = await self.db.execute(stmt)
        pricing = result.scalar_one_or_none()

        if not pricing:
            logger.warning(
                "model_price_not_found_for_date",
                model=model_name,
                at_date=at_date.isoformat(),
            )
            return None

        logger.debug(
            "model_price_retrieved_for_date",
            model=model_name,
            at_date=at_date.isoformat(),
            effective_from=pricing.effective_from.isoformat(),
        )

        return ModelPrice(
            model_name=pricing.model.model_name,
            input_price=pricing.input_unit_price,
            cached_input_price=pricing.cached_input_unit_price,
            output_price=pricing.output_unit_price,
            pricing_unit=pricing.pricing_unit.value,
            effective_from=pricing.effective_from,
            time_slots=pricing.time_slots,
        )

    async def calculate_token_cost_at_date(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int,
        at_date: datetime,
    ) -> float:
        """
        Calculate LLM token cost in EUR using historical pricing.

        Uses pricing effective at the specified date to calculate cost.
        This ensures correct cost calculation for historical messages.

        Args:
            model: LLM model name (e.g., "gpt-4.1-mini", "o1-mini-2024-09-12")
            input_tokens: Number of input/prompt tokens
            output_tokens: Number of output/completion tokens
            cached_tokens: Number of cached input tokens
            at_date: Date/time for which to retrieve pricing

        Returns:
            Cost in EUR as float

        Example:
            >>> service = AsyncPricingService(db)
            >>> cost = await service.calculate_token_cost_at_date(
            ...     "gpt-4.1-mini", 1000, 500, 200, datetime(2024, 1, 15)
            ... )
            >>> print(f"{cost:.6f}€")
            0.005813€

        Raises:
            ValueError: If currency rate not found (no fallback available)
        """
        from src.core.config import settings
        from src.core.llm_utils import normalize_model_name

        # Normalize model name (remove date suffix like -2024-09-12)
        model_normalized = normalize_model_name(model)

        # Get model pricing at historical date
        pricing = await self.get_model_price_at_date(model_normalized, at_date)

        if not pricing:
            logger.warning(
                "llm_pricing_not_found_for_date_using_zero_cost",
                model=model,
                model_normalized=model_normalized,
                at_date=at_date.isoformat(),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            return 0.0

        # Token-based costing only applies to per_1m_tokens pricing.
        # Audio-billed models (STT/TTS) must go through
        # get_cached_cost_audio_usd_eur() instead.
        if pricing.pricing_unit != "per_1m_tokens":
            logger.warning(
                "token_cost_called_for_non_token_pricing_unit",
                model=model,
                pricing_unit=pricing.pricing_unit,
            )
            return 0.0

        # Shared per-million arithmetic; the slot (if any) is resolved at the
        # HISTORICAL instant so a peak-hour message keeps its peak cost.
        total_cost_usd = _token_cost_usd(
            pricing, input_tokens, output_tokens, cached_tokens, at_date
        )

        # Convert to EUR (configured default currency)
        if settings.default_currency.upper() == _CURRENCY_EUR:
            try:
                # Hybrid logic: Try API live → Fallback DB
                from src.infrastructure.external.currency_api import CurrencyRateService

                api = CurrencyRateService()
                usd_to_eur_rate_decimal = await api.get_rate(_CURRENCY_USD, _CURRENCY_EUR)

                if usd_to_eur_rate_decimal:
                    # API success - use live rate
                    total_cost_eur = total_cost_usd * float(usd_to_eur_rate_decimal)
                    logger.debug(
                        "cost_converted_usd_to_eur_for_historical_date",
                        source="api_live",
                        model=model_normalized,
                        at_date=at_date.isoformat(),
                        rate=float(usd_to_eur_rate_decimal),
                        usd=total_cost_usd,
                        eur=total_cost_eur,
                    )
                else:
                    # Fallback to DB (last synced rate)
                    db_rate = await self.get_active_currency_rate(_CURRENCY_USD, _CURRENCY_EUR)
                    total_cost_eur = total_cost_usd * float(db_rate)
                    logger.warning(
                        "cost_converted_usd_to_eur_fallback_db_for_historical_date",
                        source="database_fallback",
                        model=model_normalized,
                        at_date=at_date.isoformat(),
                        rate=float(db_rate),
                        usd=total_cost_usd,
                        eur=total_cost_eur,
                    )
            except ValueError:
                # No rate in DB - cannot convert, use USD as fallback
                logger.warning(
                    "currency_conversion_failed_fallback_to_usd_for_historical_date",
                    model=model_normalized,
                    at_date=at_date.isoformat(),
                    cost_usd=total_cost_usd,
                )
                return total_cost_usd
        else:
            # Default currency is USD - no conversion needed
            total_cost_eur = total_cost_usd

        return total_cost_eur

    async def calculate_token_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
        at: datetime | None = None,
    ) -> tuple[float, float]:
        """
        Calculate LLM token cost in USD and configured currency (EUR).

        Centralized cost calculation logic used by callbacks, tracking,
        and statistics. Single source of truth for token cost computation.

        Args:
            model: LLM model name (e.g., "gpt-4.1-mini", "o1-mini-2024-09-12")
            input_tokens: Number of input/prompt tokens
            output_tokens: Number of output/completion tokens
            cached_tokens: Number of cached input tokens (default: 0)
            at: Billing instant used for time-slot tariff resolution
                (ADR-223). Defaults to now (UTC) — the call instant.

        Returns:
            Tuple of (cost_usd, cost_eur) as floats

        Example:
            >>> service = AsyncPricingService(db)
            >>> usd, eur = await service.calculate_token_cost("gpt-4.1-mini", 1000, 500, 200)
            >>> print(f"${usd:.6f} / {eur:.6f}€")
            $0.006250 / 0.005813€

        Raises:
            ValueError: If currency rate not found (no fallback available)
        """
        from src.core.config import settings
        from src.core.llm_utils import normalize_model_name

        # Normalize model name (remove date suffix like -2024-09-12)
        model_normalized = normalize_model_name(model)

        # Get model pricing from database
        pricing = await self.get_active_model_price(model_normalized)

        if not pricing:
            logger.warning(
                "llm_pricing_not_found_using_zero_cost",
                model=model,
                model_normalized=model_normalized,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            return (0.0, 0.0)

        # Token-based costing only applies to per_1m_tokens pricing.
        # Audio-billed models (STT/TTS) must go through
        # get_cached_cost_audio_usd_eur() instead.
        if pricing.pricing_unit != "per_1m_tokens":
            logger.warning(
                "token_cost_called_for_non_token_pricing_unit",
                model=model,
                pricing_unit=pricing.pricing_unit,
            )
            return (0.0, 0.0)

        # Shared per-million arithmetic; the slot (if any) is resolved at the
        # billing instant — the call time unless the caller pins one.
        total_cost_usd = _token_cost_usd(
            pricing, input_tokens, output_tokens, cached_tokens, at or datetime.now(UTC)
        )

        # Convert to EUR (configured default currency)
        if settings.default_currency.upper() == _CURRENCY_EUR:
            try:
                # Hybrid logic: Try API live → Fallback DB
                from src.infrastructure.external.currency_api import CurrencyRateService

                api = CurrencyRateService()
                usd_to_eur_rate_decimal = await api.get_rate(_CURRENCY_USD, _CURRENCY_EUR)

                if usd_to_eur_rate_decimal:
                    # API success - use live rate
                    total_cost_eur = total_cost_usd * float(usd_to_eur_rate_decimal)
                    logger.debug(
                        "cost_converted_usd_to_eur",
                        source="api_live",
                        model=model_normalized,
                        rate=float(usd_to_eur_rate_decimal),
                        usd=total_cost_usd,
                        eur=total_cost_eur,
                    )
                else:
                    # Fallback to DB (last synced rate)
                    db_rate = await self.get_active_currency_rate(_CURRENCY_USD, _CURRENCY_EUR)
                    total_cost_eur = total_cost_usd * float(db_rate)
                    logger.warning(
                        "cost_converted_usd_to_eur_fallback_db",
                        source="database_fallback",
                        model=model_normalized,
                        rate=float(db_rate),
                        usd=total_cost_usd,
                        eur=total_cost_eur,
                    )
            except ValueError:
                # No rate in DB - cannot convert, use USD for both (fallback)
                logger.warning(
                    "currency_conversion_failed_fallback_to_usd",
                    model=model_normalized,
                    cost_usd=total_cost_usd,
                )
                return (total_cost_usd, total_cost_usd)
        else:
            # Default currency is USD - no conversion needed
            total_cost_eur = total_cost_usd

        return (total_cost_usd, total_cost_eur)

    def _invalidate_cache(self, cache_key: str) -> None:
        """
        Invalidate specific cache entry.

        Removes cache timestamp and cached data to force fresh query on next access.
        """
        if cache_key in self._cache_timestamp:
            del self._cache_timestamp[cache_key]
        if cache_key in self._model_price_cache:
            del self._model_price_cache[cache_key]
        if cache_key in self._currency_rate_cache:
            del self._currency_rate_cache[cache_key]

    def invalidate_all_caches(self) -> None:
        """
        Invalidate all cached pricing and currency data.

        Useful after bulk pricing updates or administrative changes.
        """
        self._cache_timestamp.clear()
        self._model_price_cache.clear()
        self._currency_rate_cache.clear()
        logger.info("all_async_pricing_caches_invalidated")
