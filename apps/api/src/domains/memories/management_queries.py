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
from sqlalchemy.sql.elements import ColumnElement

from src.core.exceptions import ResourceNotFoundError
from src.domains.memories.models import Memory

_COUNTS = TypeAdapter(dict[str, Annotated[StrictInt, Field(ge=0)]])


@dataclass(frozen=True)
class MemoryManagementPage:
    rows: list[Memory]
    by_category: dict[str, int]
    biometric_ids: frozenset[UUID] = frozenset()


def _visible_conditions(
    actor_id: UUID,
    *,
    exclude_categories: tuple[str, ...],
    exclude_biometric: bool,
    query: str | None,
    recorded_start: datetime | None,
    recorded_end: datetime | None,
) -> tuple[ColumnElement[bool], ...]:
    visible: tuple[ColumnElement[bool], ...] = (
        Memory.user_id == actor_id,
        Memory.invalidated_at.is_(None),
    )
    if exclude_categories:
        visible += (Memory.category.not_in(exclude_categories),)
    if exclude_biometric:
        visible += (Memory.context_biometric.is_(None),)
    if recorded_start is not None:
        visible += (Memory.created_at >= recorded_start,)
    if recorded_end is not None:
        visible += (Memory.created_at < recorded_end,)
    if query is not None:
        visible += (
            (
                Memory.content.icontains(query, autoescape=True)
                | Memory.trigger_topic.icontains(query, autoescape=True)
            ),
        )
    return visible


async def read_management_page(
    db: AsyncSession,
    actor_id: UUID,
    *,
    limit: int,
    category: str | None = None,
    memory_id: UUID | None = None,
    after_id: UUID | None = None,
    exclude_categories: tuple[str, ...] = (),
    exclude_biometric: bool = False,
    query: str | None = None,
    recorded_start: datetime | None = None,
    recorded_end: datetime | None = None,
) -> MemoryManagementPage:
    """The empty-page anchor keeps uncapped counts available even beyond the last cursor."""
    visible = _visible_conditions(
        actor_id,
        exclude_categories=exclude_categories,
        exclude_biometric=exclude_biometric,
        query=query,
        recorded_start=recorded_start,
        recorded_end=recorded_end,
    )
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
        select(Memory, counts.c.by_category, anchor_time, Memory.context_biometric.is_not(None))
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
    result: Result[tuple[Memory | None, object, datetime | None, bool]] = await db.execute(
        statement
    )
    rows = result.all()
    if after_id is not None and rows[0][2] is None:
        raise ResourceNotFoundError("memory cursor", str(after_id))
    return MemoryManagementPage(
        rows=[memory for memory, _, _, _ in rows if memory is not None],
        by_category=_COUNTS.validate_python(rows[0][1]),
        biometric_ids=frozenset(
            memory.id for memory, _, _, has_bio in rows if memory is not None and has_bio
        ),
    )
