"""Tenant/binding/evidence-scoped ephemeral annotations; never source text in Redis."""

import asyncio
import hashlib
import json
import math
from datetime import datetime
from uuid import UUID

from pydantic import TypeAdapter
from redis.asyncio import Redis

from src.core.constants import (
    JEV_CLASSIFICATION_CACHE_TIMEOUT_SECONDS,
    JEV_CLASSIFICATION_EMAIL_TTL_SECONDS,
    JEV_CLASSIFICATION_EVENT_TTL_SECONDS,
)
from src.core.content_classification import ContentClassification
from src.domains.agents.services.qualification.contracts import (
    ClassificationObservation,
)
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)
_ANNOTATION: TypeAdapter[ContentClassification] = TypeAdapter(ContentClassification)


def classification_cache_key(
    observation: ClassificationObservation,
    *,
    user_id: UUID,
    provider: str,
    source_scope: str,
    model: str,
    policy: str,
    now: datetime,
    timezone: str,
) -> str:
    ttl = (
        JEV_CLASSIFICATION_EMAIL_TTL_SECONDS
        if observation.kind == "email"
        else JEV_CLASSIFICATION_EVENT_TTL_SECONDS
    )
    fingerprint = {
        "provider": provider,
        "binding": source_scope,
        "model": model,
        "policy": policy,
        "reference_bucket": int(now.timestamp()) // ttl,
        "timezone": timezone,
        "observation": observation.model_dump(mode="json", exclude={"identity"}),
    }
    digest = hashlib.sha256(
        json.dumps(fingerprint, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()
    return f"content:classification:{user_id}:{digest}"


class ClassificationCache:
    def __init__(self, client: Redis | None) -> None:
        self.client = client

    async def read(
        self,
        keys: dict[str, str],
        observations: list[ClassificationObservation],
        now: datetime,
    ) -> dict[str, ContentClassification]:
        if self.client is None or not keys:
            return {}
        try:
            async with asyncio.timeout(JEV_CLASSIFICATION_CACHE_TIMEOUT_SECONDS):
                rows = await self.client.mget(list(keys.values()))
            if len(rows) != len(keys):
                return {}
            scopes = {value.identity: value.evidence_scope for value in observations}
            kinds = {value.identity: value.kind for value in observations}
            result: dict[str, ContentClassification] = {}
            for (identity, _), raw in zip(keys.items(), rows, strict=True):
                if not isinstance(raw, str | bytes):
                    continue
                accepted = _cached_annotation(raw, now)
                if (
                    accepted is not None
                    and accepted.kind == kinds[identity]
                    and accepted.evidence_scope == scopes[identity]
                ):
                    result[identity] = accepted
            return result
        except Exception as exc:
            self.client = None
            logger.debug("classification_cache_read_unavailable", error_type=type(exc).__name__)
            return {}

    async def write(
        self,
        keys: dict[str, str],
        values: dict[str, ContentClassification],
        now: datetime,
    ) -> None:
        if self.client is None or not values:
            return
        try:
            async with asyncio.timeout(JEV_CLASSIFICATION_CACHE_TIMEOUT_SECONDS):
                async with self.client.pipeline(transaction=False) as pipeline:
                    for identity, value in values.items():
                        ttl = max(1, math.ceil((value.valid_until - now).total_seconds()))
                        pipeline.set(keys[identity], value.model_dump_json(), ex=ttl)
                    await pipeline.execute()
        except Exception as exc:
            logger.debug("classification_cache_write_unavailable", error_type=type(exc).__name__)


def _cached_annotation(raw: str | bytes, now: datetime) -> ContentClassification | None:
    try:
        result = _ANNOTATION.validate_json(raw)
        limit = (
            JEV_CLASSIFICATION_EMAIL_TTL_SECONDS
            if result.kind == "email"
            else JEV_CLASSIFICATION_EVENT_TTL_SECONDS
        )
        if (
            result.evaluated_at <= now < result.valid_until
            and (result.valid_until - result.evaluated_at).total_seconds() <= limit
        ):
            return result
    except ValueError:
        return None  # Malformed optional cache data is a miss, never authority.
    return None


async def open_classification_cache() -> ClassificationCache:
    try:
        return ClassificationCache(await get_redis_cache())
    except Exception as exc:
        logger.debug("classification_cache_unavailable", error_type=type(exc).__name__)
        return ClassificationCache(None)
