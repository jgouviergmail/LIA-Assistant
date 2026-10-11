"""Explicit owned management reads neither search embeddings nor increment recall usage."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceNotFoundError
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.memory_read_schemas import MemoryProjection, MemoryRead
from src.domains.memories.management_queries import read_management_page
from src.domains.memories.read_models import build_retention_config, memory_to_response


async def read_memories(db: AsyncSession, actor_id: UUID, request: MemoryRead) -> MemoryProjection:
    selected = MemoryRead.model_validate(request.model_dump())
    await require_application_tools(db)
    await load_actor(db, actor_id)
    page = await read_management_page(
        db,
        actor_id,
        limit=selected.limit,
        category=selected.category,
        memory_id=selected.memory_id,
        after_id=selected.after_id,
    )
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    if selected.memory_id is not None and not page.rows:
        raise ResourceNotFoundError("memory", str(selected.memory_id))
    rows = page.rows[: selected.limit]
    more = len(page.rows) > selected.limit
    now, policy = datetime.now(UTC), build_retention_config()
    total = (
        1
        if selected.memory_id is not None
        else (
            page.by_category.get(selected.category, 0)
            if selected.category is not None
            else sum(page.by_category.values())
        )
    )
    result = MemoryProjection(
        memories=[memory_to_response(row, now, policy) for row in rows],
        automatic_use_enabled=actor.memory_enabled,
        returned_count=len(rows),
        total_available=total,
        by_category=page.by_category,
        truncated=more,
        next_cursor=rows[-1].id if more else None,
    )
    return result
