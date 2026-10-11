"""Bounded active-memory rows and complete category counts from one SQL snapshot."""

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import Field, StrictInt, TypeAdapter
from sqlalchemy import Result, func, literal, select, tuple_
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, defer

from src.core.exceptions import ResourceNotFoundError
from src.domains.memories.models import Memory

_COUNTS = TypeAdapter(dict[str, Annotated[StrictInt, Field(ge=0)]])


@dataclass(frozen=True)
class MemoryManagementPage:
    rows: list[Memory]
    by_category: dict[str, int]


async def read_management_page(
    db: AsyncSession,
    actor_id: UUID,
    *,
    limit: int,
    category: str | None = None,
    memory_id: UUID | None = None,
    after_id: UUID | None = None,
) -> MemoryManagementPage:
    """The empty-page anchor keeps uncapped counts available even beyond the last cursor."""
    visible = (Memory.user_id == actor_id, Memory.invalidated_at.is_(None))
    groups = (
        select(Memory.category.label("category"), func.count().label("count"))
        .where(*visible)
        .group_by(Memory.category)
        .cte("memory_categories")
    )
    counts = (
        select(
            func.coalesce(
                func.jsonb_object_agg(groups.c.category, groups.c.count), literal({}, type_=JSONB)
            ).label("by_category")
        )
        .select_from(groups)
        .subquery()
    )
    selection = select(Memory.id).where(*visible)
    anchor = aliased(Memory)
    anchor_time = (
        select(anchor.created_at)
        .where(anchor.user_id == actor_id, anchor.id == after_id)
        .scalar_subquery()
    )
    if category is not None:
        selection = selection.where(Memory.category == category)
    if memory_id is not None:
        selection = selection.where(Memory.id == memory_id)
    if after_id is not None:
        selection = selection.where(
            tuple_(Memory.created_at, Memory.id) < tuple_(anchor_time, literal(after_id))
        )
    page = (
        selection.order_by(Memory.created_at.desc(), Memory.id.desc())
        .limit(limit + 1)
        .cte("memory_page")
    )
    statement = (
        select(Memory, counts.c.by_category, anchor_time)
        .options(
            defer(Memory.embedding),
            defer(Memory.keyword_embedding),
            defer(Memory.context_biometric),
        )
        .select_from(counts)
        .outerjoin(Memory, Memory.id.in_(select(page.c.id)))
        .order_by(Memory.created_at.desc(), Memory.id.desc())
        .execution_options(populate_existing=True)
    )
    result: Result[tuple[Memory | None, object, datetime | None]] = await db.execute(statement)
    rows = result.all()
    if after_id is not None and rows[0][2] is None:
        raise ResourceNotFoundError("memory cursor", str(after_id))
    return MemoryManagementPage(
        rows=[memory for memory, _, _ in rows if memory is not None],
        by_category=_COUNTS.validate_python(rows[0][1]),
    )
