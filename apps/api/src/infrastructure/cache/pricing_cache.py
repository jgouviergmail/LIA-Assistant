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
    Cached pricing for a single LLM model in USD.

    The semantic of the unit prices is given by ``pricing_unit``:
    - ``per_1m_tokens``: price per 1 million tokens (LLM chat/text). Default.
    - ``per_audio_minute`` / ``per_audio_hour``: price per audio duration
      (STT/TTS).

    Stored in Redis as JSON for fast retrieval in callbacks.
    """

    input_unit_price: float
    output_unit_price: float
    cached_input_unit_price: float  # 0.0 if caching not supported by model
    pricing_unit: str = "per_1m_tokens"

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
        from sqlalchemy.orm import selectinload

        from src.domains.llm.models import LLMModelPricing
        from src.domains.llm.pricing_service import AsyncPricingService
        from src.infrastructure.database import get_db_context

        try:
            async with get_db_context() as session:
                # Load all active model prices, eagerly fetching the model row
                # so pricing.model.model_name does not trigger a lazy-load
                # (LLMModelPricing.model uses lazy="raise").
                stmt = (
                    select(LLMModelPricing)
                    .options(selectinload(LLMModelPricing.model))
                    .where(LLMModelPricing.is_active)
                )
                result = await session.scalars(stmt)

                models: dict[str, CachedModelPrice] = {}
                for pricing in result.all():
                    models[pricing.model.model_name] = CachedModelPrice(
                        input_unit_price=float(pricing.input_unit_price),
                        output_unit_price=float(pricing.output_unit_price),
                        cached_input_unit_price=float(pricing.cached_input_unit_price or 0),
                        pricing_unit=pricing.pricing_unit.value,
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

        Called at startup if Redis already has cached data. Returns False
        (forcing a rebuild from DB) if the serialised payload is incompatible
        — e.g. after a column rename when the previous deploy left an old
        format in Redis.

        Returns:
            True if cache was loaded, False if not found or schema mismatch
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
        except (KeyError, TypeError, ValueError) as e:
            # Redis blob is in an old/incompatible shape (e.g. produced by
            # a previous deploy before the column rename). Drop it; the
            # caller will refresh from DB.
            logger.warning(
                "pricing_cache_redis_blob_incompatible_dropping",
                error=str(e),
                error_type=type(e).__name__,
            )
            try:
                await self.redis.delete(self._cache_key)
            except Exception:  # noqa: BLE001
                pass
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

    async def invalidate_and_refresh(self) -> bool:
        """Refresh pricing cache and notify all workers.

        Called by admin endpoints after pricing modifications.
        Publishes cross-worker invalidation via Redis Pub/Sub (ADR-063).

        Returns:
            True if refresh succeeded, False otherwise.
        """
        from src.core.constants import CACHE_NAME_PRICING
        from src.infrastructure.cache.invalidation import publish_cache_invalidation

        success = await self.refresh_from_database()
        if success:
            await publish_cache_invalidation(CACHE_NAME_PRICING)
        return success


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

    Token-based costing only applies to ``pricing_unit='per_1m_tokens'`` models.
    Audio-billed models (STT/TTS) must go through
    :func:`get_cached_cost_audio_usd_eur` instead.

    Args:
        model: LLM model name (e.g., "gpt-4.1-mini", "o1-mini")
        prompt_tokens: Number of prompt/input tokens
        completion_tokens: Number of completion/output tokens
        cached_tokens: Number of cached input tokens (default: 0)

    Returns:
        Tuple of (cost_usd, cost_eur) as floats
        Returns (0.0, 0.0) if cache not initialized, model not found, or
        the model uses a non-token pricing unit.
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

    if prices.pricing_unit != "per_1m_tokens":
        logger.warning(
            "token_cost_called_for_non_token_pricing_unit",
            model=model,
            pricing_unit=prices.pricing_unit,
        )
        return (0.0, 0.0)

    # Calculate cost (USD per 1M tokens)
    input_cost = (prompt_tokens / 1_000_000) * prices.input_unit_price
    output_cost = (completion_tokens / 1_000_000) * prices.output_unit_price
    cached_cost = (cached_tokens / 1_000_000) * prices.cached_input_unit_price

    total_usd = input_cost + output_cost + cached_cost
    total_eur = total_usd * _local_cache.usd_eur_rate

    return (total_usd, total_eur)


def get_cached_cost_audio_usd_eur(
    model: str,
    duration_seconds: float,
) -> tuple[float, float]:
    """
    Estimate audio-billed cost (STT/TTS) in both USD and EUR (sync-safe).

    Mirror of :func:`get_cached_cost_usd_eur` for models priced by audio
    duration rather than tokens. Selects the multiplier based on
    ``pricing_unit``:

    - ``per_audio_hour`` (e.g. ElevenLabs Scribe at $0.22/hour):
      ``cost_usd = duration_seconds / 3600 * input_unit_price``
    - ``per_audio_minute``:
      ``cost_usd = duration_seconds / 60 * input_unit_price``

    Args:
        model: STT/TTS model name (e.g., "scribe_v2")
        duration_seconds: Duration of the audio segment in seconds

    Returns:
        Tuple of (cost_usd, cost_eur) as floats. Returns (0.0, 0.0) if cache
        not initialized, model not found, or the model is token-priced
        (caller should use ``get_cached_cost_usd_eur`` instead).
    """
    if _local_cache is None:
        logger.debug("pricing_cache_not_initialized", model=model)
        pricing_cache_fallback_total.labels(reason="cache_not_initialized").inc()
        return (0.0, 0.0)

    if duration_seconds <= 0:
        return (0.0, 0.0)

    model_normalized = normalize_model_name(model)
    prices = _local_cache.models.get(model_normalized)

    if not prices:
        logger.debug(
            "pricing_cache_audio_model_not_found",
            model=model,
            model_normalized=model_normalized,
            available_models=len(_local_cache.models),
        )
        pricing_cache_fallback_total.labels(reason="model_not_found").inc()
        return (0.0, 0.0)

    if prices.pricing_unit == "per_audio_hour":
        cost_usd = (duration_seconds / 3600.0) * prices.input_unit_price
    elif prices.pricing_unit == "per_audio_minute":
        cost_usd = (duration_seconds / 60.0) * prices.input_unit_price
    else:
        logger.warning(
            "audio_cost_called_for_non_audio_pricing_unit",
            model=model,
            pricing_unit=prices.pricing_unit,
        )
        return (0.0, 0.0)

    cost_eur = cost_usd * _local_cache.usd_eur_rate
    return (cost_usd, cost_eur)


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
