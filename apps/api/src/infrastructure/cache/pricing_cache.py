"""
Pricing Cache Service for LLM cost estimation in callbacks.

Provides a Redis-backed cache for LLM pricing data that can be read synchronously
in LangChain callbacks without requiring DB access (avoiding asyncio event loop issues).

Architecture:
    DB (LLMModelPricing) → AsyncPricingService → Redis Cache → Sync read in callbacks

Usage:
    # At startup (async context)
    await refresh_pricing_cache()

    # In callbacks (sync-safe)
    cost = get_cached_cost("gpt-4.1-mini", 1000, 500, 200)

Reference: ADR-039-Cost-Optimization-Token-Management.md
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import structlog
from prometheus_client import Counter

from src.core.config import settings
from src.core.constants import REDIS_KEY_PRICING_CACHE, SUPPORTED_CURRENCIES
from src.core.llm_utils import normalize_model_name

# Currency constants (LLM pricing is in USD, with optional conversion to EUR)
# Extracted from SUPPORTED_CURRENCIES to ensure type safety and consistency
_CURRENCY_USD = SUPPORTED_CURRENCIES[0]  # "USD"
_CURRENCY_EUR = SUPPORTED_CURRENCIES[1]  # "EUR"


# ============================================================================
# PROTOCOLS (for type-safe duck typing)
# ============================================================================


@runtime_checkable
class TokenUsageRecord(Protocol):
    """
    Protocol for token usage records (duck typing interface).

    Any object with these attributes can be used with calculate_total_cost_from_logs().
    Typically: TokenUsageLog model from src.domains.chat.models
    """

    model_name: str
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int | None


# ============================================================================
# PROMETHEUS METRICS
# ============================================================================
# Track fallback scenarios for monitoring and alerting

pricing_cache_fallback_total = Counter(
    "pricing_cache_fallback_total",
    "Total pricing cache fallbacks (cost returned as 0.0)",
    ["reason"],  # "cache_not_initialized", "model_not_found"
)

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = structlog.get_logger(__name__)


# ============================================================================
# DATA STRUCTURES
# ============================================================================


@dataclass
class CachedModelPrice:
    """
    Cached pricing for a single LLM model (USD per 1M tokens).

    Stored in Redis as JSON for fast retrieval in callbacks.
    """

    input_price_per_1m: float
    output_price_per_1m: float
    cached_input_price_per_1m: float  # 0.0 if caching not supported by model

    def to_json(self) -> str:
        """Serialize to JSON for Redis storage."""
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> CachedModelPrice:
        """Deserialize from Redis JSON."""
        parsed = json.loads(data)
        return cls(**parsed)


@dataclass
class PricingCacheData:
    """
    Complete pricing cache data stored in Redis.

    Single Redis key contains all model prices + exchange rate for atomic updates.
    """

    models: dict[str, CachedModelPrice]
    usd_eur_rate: float
    last_refresh_ts: float  # Unix timestamp

    def to_json(self) -> str:
        """Serialize to JSON for Redis storage."""
        return json.dumps(
            {
                "models": {k: asdict(v) for k, v in self.models.items()},
                "usd_eur_rate": self.usd_eur_rate,
                "last_refresh_ts": self.last_refresh_ts,
            }
        )

    @classmethod
    def from_json(cls, data: str) -> PricingCacheData:
        """Deserialize from Redis JSON."""
        parsed = json.loads(data)
        models = {k: CachedModelPrice(**v) for k, v in parsed["models"].items()}
        return cls(
            models=models,
            usd_eur_rate=parsed["usd_eur_rate"],
            last_refresh_ts=parsed["last_refresh_ts"],
        )


# ============================================================================
# CACHE SERVICE
# ============================================================================

# Module-level cache for sync access (populated from Redis)
_local_cache: PricingCacheData | None = None


class PricingCacheService:
    """
    Service for managing LLM pricing cache in Redis.

    Provides async methods for cache refresh and sync methods for cost estimation.
    Uses AsyncPricingService as the source of truth for pricing data.
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        """
        Initialize pricing cache service.

        Args:
            redis_client: Redis client from get_redis_cache()
        """
        self.redis = redis_client
        self._cache_key = REDIS_KEY_PRICING_CACHE

    async def refresh_from_database(self) -> bool:
        """
        Refresh pricing cache from database using AsyncPricingService.

        Loads all active model prices and current USD/EUR rate,
        then stores them in Redis for sync access.

        Returns:
            True if refresh succeeded, False otherwise
        """
        global _local_cache
        import time

        from sqlalchemy import select

        from src.domains.llm.models import LLMModelPricing
        from src.domains.llm.pricing_service import AsyncPricingService
        from src.infrastructure.database import get_db_context

        try:
            async with get_db_context() as session:
                # Load all active model prices
                stmt = select(LLMModelPricing).where(LLMModelPricing.is_active)
                result = await session.scalars(stmt)

                models: dict[str, CachedModelPrice] = {}
                for pricing in result.all():
                    models[pricing.model_name] = CachedModelPrice(
                        input_price_per_1m=float(pricing.input_price_per_1m_tokens),
                        output_price_per_1m=float(pricing.output_price_per_1m_tokens),
                        cached_input_price_per_1m=float(
                            pricing.cached_input_price_per_1m_tokens or 0
                        ),
                    )

                # Load USD/EUR rate using existing service
                # Fallback to settings.default_usd_eur_rate (from .env or constants.py)
                usd_eur_rate = settings.default_usd_eur_rate
                try:
                    pricing_service = AsyncPricingService(
                        session,
                        cache_ttl_seconds=settings.llm_pricing_cache_ttl_seconds,
                    )
                    rate = await pricing_service.get_active_currency_rate(
                        _CURRENCY_USD, _CURRENCY_EUR
                    )
                    usd_eur_rate = float(rate)
                except ValueError:
                    logger.warning(
                        "pricing_cache_currency_rate_unavailable",
                        fallback_rate=settings.default_usd_eur_rate,
                    )

            # Create cache data
            cache_data = PricingCacheData(
                models=models,
                usd_eur_rate=usd_eur_rate,
                last_refresh_ts=time.time(),
            )

            # Store in Redis with TTL from settings
            ttl_seconds = settings.llm_pricing_cache_ttl_seconds
            await self.redis.setex(
                self._cache_key,
                ttl_seconds,
                cache_data.to_json(),
            )

            # Update local cache for sync access
            _local_cache = cache_data

            logger.info(
                "pricing_cache_refreshed",
                models_count=len(models),
                usd_eur_rate=usd_eur_rate,
                ttl_seconds=ttl_seconds,
            )
            return True

        except Exception as e:
            logger.error(
                "pricing_cache_refresh_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            return False

    async def load_from_redis(self) -> bool:
        """
        Load pricing cache from Redis into local memory.

        Called at startup if Redis already has cached data.

        Returns:
            True if cache was loaded, False if not found or error
        """
        global _local_cache

        try:
            data = await self.redis.get(self._cache_key)
            if data:
                _local_cache = PricingCacheData.from_json(data)
                logger.info(
                    "pricing_cache_loaded_from_redis",
                    models_count=len(_local_cache.models),
                )
                return True
            return False
        except Exception as e:
            logger.warning(
                "pricing_cache_load_failed",
                error=str(e),
            )
            return False

    async def invalidate(self) -> None:
        """Invalidate pricing cache (force refresh on next access)."""
        global _local_cache
        _local_cache = None
        await self.redis.delete(self._cache_key)
        logger.info("pricing_cache_invalidated")


# ============================================================================
# MODULE-LEVEL FUNCTIONS (for use in callbacks)
# ============================================================================


def get_cached_cost_usd_eur(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: int = 0,
) -> tuple[float, float]:
    """
    Estimate cost in both USD and EUR using cached prices (sync-safe for callbacks).

    This function is synchronous and reads from in-memory cache populated
    from Redis, avoiding any DB access or async operations.

    Mirrors AsyncPricingService.calculate_token_cost() return signature for consistency.

    Args:
        model: LLM model name (e.g., "gpt-4.1-mini", "o1-mini")
        prompt_tokens: Number of prompt/input tokens
        completion_tokens: Number of completion/output tokens
        cached_tokens: Number of cached input tokens (default: 0)

    Returns:
        Tuple of (cost_usd, cost_eur) as floats
        Returns (0.0, 0.0) if cache not initialized or model not found
    """
    if _local_cache is None:
        logger.debug("pricing_cache_not_initialized", model=model)
        pricing_cache_fallback_total.labels(reason="cache_not_initialized").inc()
        return (0.0, 0.0)

    model_normalized = normalize_model_name(model)
    prices = _local_cache.models.get(model_normalized)

    if not prices:
        logger.debug(
            "pricing_cache_model_not_found",
            model=model,
            model_normalized=model_normalized,
            available_models=len(_local_cache.models),
        )
        pricing_cache_fallback_total.labels(reason="model_not_found").inc()
        return (0.0, 0.0)

    # Calculate cost (USD per 1M tokens)
    input_cost = (prompt_tokens / 1_000_000) * prices.input_price_per_1m
    output_cost = (completion_tokens / 1_000_000) * prices.output_price_per_1m
    cached_cost = (cached_tokens / 1_000_000) * prices.cached_input_price_per_1m

    total_usd = input_cost + output_cost + cached_cost
    total_eur = total_usd * _local_cache.usd_eur_rate

    return (total_usd, total_eur)


def get_cached_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: int = 0,
) -> float:
    """
    Estimate cost using cached prices (sync-safe for callbacks).

    This function is synchronous and reads from in-memory cache populated
    from Redis, avoiding any DB access or async operations.

    Args:
        model: LLM model name (e.g., "gpt-4.1-mini", "o1-mini")
        prompt_tokens: Number of prompt/input tokens
        completion_tokens: Number of completion/output tokens
        cached_tokens: Number of cached input tokens (default: 0)

    Returns:
        Estimated cost in configured currency (EUR if settings.default_currency == "EUR")
        Returns 0.0 if model not found in cache
    """
    cost_usd, cost_eur = get_cached_cost_usd_eur(
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_tokens=cached_tokens,
    )

    # Return cost in configured currency
    if settings.default_currency.upper() == _CURRENCY_EUR:
        return cost_eur

    return cost_usd


def calculate_total_cost_from_logs(logs: Iterable[TokenUsageRecord]) -> float:
    """
    Calculate total cost from a collection of token usage logs.

    Centralized helper to avoid code duplication across services.
    Uses cached pricing (sync-safe, no DB/API calls).

    Args:
        logs: Iterable of objects implementing TokenUsageRecord protocol
              (typically TokenUsageLog from src.domains.chat.models)

    Returns:
        Total cost in configured currency (EUR if settings.default_currency == "EUR")
        Returns 0.0 if cache not initialized or models not found

    Example:
        >>> logs = await chat_repo.get_token_logs_by_run_id(run_id)
        >>> total_cost = calculate_total_cost_from_logs(logs)
    """
    return sum(
        get_cached_cost(
            model=log.model_name,
            prompt_tokens=log.prompt_tokens,
            completion_tokens=log.completion_tokens,
            cached_tokens=log.cached_tokens or 0,
        )
        for log in logs
    )


def is_cache_initialized() -> bool:
    """Check if pricing cache is initialized and available."""
    return _local_cache is not None


def get_cached_usd_eur_rate() -> float:
    """
    Get USD/EUR exchange rate from cache (sync-safe).

    Returns the cached exchange rate, or falls back to settings.default_usd_eur_rate
    if cache is not initialized.

    Returns:
        USD to EUR exchange rate (e.g., 0.93 means 1 USD = 0.93 EUR)
    """
    if _local_cache is None:
        return settings.default_usd_eur_rate

    return _local_cache.usd_eur_rate


def get_cache_stats() -> dict:
    """Get pricing cache statistics for monitoring."""
    if _local_cache is None:
        return {"initialized": False, "models_count": 0}

    return {
        "initialized": True,
        "models_count": len(_local_cache.models),
        "usd_eur_rate": _local_cache.usd_eur_rate,
        "last_refresh_ts": _local_cache.last_refresh_ts,
    }


# ============================================================================
# INITIALIZATION HELPER
# ============================================================================


async def refresh_pricing_cache() -> bool:
    """
    Refresh pricing cache from database.

    Convenience function for use in app startup. Creates service instance
    and refreshes cache from DB.

    Returns:
        True if refresh succeeded, False otherwise
    """
    try:
        from src.infrastructure.cache.redis import get_redis_cache

        redis = await get_redis_cache()
        service = PricingCacheService(redis)

        # Try to load from Redis first (faster if already cached)
        if await service.load_from_redis():
            return True

        # Otherwise refresh from database
        return await service.refresh_from_database()

    except Exception as e:
        logger.error(
            "pricing_cache_initialization_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        return False
