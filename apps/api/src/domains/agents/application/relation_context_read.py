"""Source provider-card reads retain their quota, cache provenance and per-section outcomes."""

from datetime import UTC, datetime
from typing import get_args
from uuid import UUID

from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.relation_context_schemas import (
    RELATION_CONTEXT_MAX_BYTES,
    RelationContextProjection,
    RelationContextQuery,
    RelationProviderSection,
)
from src.domains.relations.providers.service import _ALL_SECTIONS, RelationContextService
from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter


async def acquire_relation_context_budget(actor_id: UUID) -> None:
    try:
        limiter = await get_rate_limiter()
        allowed = await limiter.acquire(
            key=f"auth:relations_context:user:{actor_id}",
            max_calls=settings.relations_provider_rate_limit_calls,
            window_seconds=settings.relations_provider_rate_limit_window_seconds,
        )
    except RedisError as exc:
        raise CommandRejected("DEPENDENCY_ERROR") from exc
    if not allowed:
        raise CommandRejected("RATE_LIMIT_EXCEEDED")


async def read_relation_context(
    db: AsyncSession, actor_id: UUID, query: RelationContextQuery
) -> RelationContextProjection:
    selected = RelationContextQuery.model_validate(query.model_dump())
    await require_application_tools(db)
    await load_actor(db, actor_id)
    if selected.sections:
        await acquire_relation_context_budget(actor_id)
        await require_application_tools(db)
        await load_actor(db, actor_id)
    observed = await RelationContextService(actor_id).build(
        selected.name, sections=frozenset(selected.sections)
    )
    await require_application_tools(db)
    await load_actor(db, actor_id)
    if len(observed.model_dump_json().encode("utf-8")) > RELATION_CONTEXT_MAX_BYTES:
        raise ValueError("Provider card exceeds the native result bound; review the Relations page")
    return RelationContextProjection(**observed.model_dump(), observed_at=datetime.now(UTC))


if set(get_args(RelationProviderSection)) != _ALL_SECTIONS:
    raise AssertionError("New provider-card sections require reviewed native selectors and quotas")
