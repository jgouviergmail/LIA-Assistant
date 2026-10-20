"""Strict distributed admission for new ingestion resources; health is unchanged."""

from redis.exceptions import RedisError

from src.core.config import settings
from src.core.constants import REDIS_KEY_INGESTION_PREFIX
from src.core.exceptions import ExternalServiceError, RateLimitError
from src.domains.ingestion.principal import IngestionPrincipal
from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter


async def require_admission(principal: IngestionPrincipal) -> None:
    try:
        limiter = await get_rate_limiter()
        buckets = (
            (
                f"{REDIS_KEY_INGESTION_PREFIX}:user:{principal.user_id}",
                settings.ingestion_user_requests_per_minute,
            ),
            (
                f"{REDIS_KEY_INGESTION_PREFIX}:source:{principal.user_id}:{principal.source_id}",
                settings.ingestion_source_requests_per_minute,
            ),
        )
        for key, limit in buckets:
            if not await limiter.acquire(key, limit, 60, fail_open=False):
                raise RateLimitError(limit, 60, 60, headers={"Retry-After": "60"})
    except RedisError:
        raise ExternalServiceError(
            "ingestion", detail="ingestion_admission_unavailable", headers={"Retry-After": "60"}
        ) from None
