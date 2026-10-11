"""Connector-list cache owner with an explicit authoritative read for committed changes."""

from uuid import UUID

import structlog

from src.domains.connectors.repository import ConnectorRepository
from src.domains.connectors.schemas import ConnectorListResponse, ConnectorResponse

logger = structlog.get_logger(__name__)


async def _database_list(repository: ConnectorRepository, actor_id: UUID) -> ConnectorListResponse:
    connectors = await repository.get_all_by_user(actor_id)
    logger.info("user_connectors_fetched", user_id=str(actor_id), count=len(connectors))
    return ConnectorListResponse(
        connectors=[ConnectorResponse.model_validate(c) for c in connectors], total=len(connectors)
    )


async def read_user_connector_list(
    repository: ConnectorRepository,
    actor_id: UUID,
    *,
    fresh: bool = False,
) -> ConnectorListResponse:
    if fresh:
        return await _database_list(repository, actor_id)
    from src.infrastructure.cache.redis import get_redis_cache

    cache_key = f"user_connectors:{actor_id}"
    redis = await get_redis_cache()
    cached = await redis.get(cache_key)
    if cached:
        logger.debug("user_connectors_cache_hit", user_id=str(actor_id))
        return ConnectorListResponse.model_validate_json(cached)
    response = await _database_list(repository, actor_id)
    await redis.set(cache_key, response.model_dump_json(), ex=300)
    return response
