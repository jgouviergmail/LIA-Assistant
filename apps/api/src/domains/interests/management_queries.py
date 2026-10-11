"""Uncapped source counts and a bounded stable interest page share one SQL snapshot."""

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
from src.domains.interests.models import UserInterest

_COUNTS = TypeAdapter(dict[str, Annotated[StrictInt, Field(ge=0)]])


@dataclass(frozen=True)
class InterestManagementPage:
    rows: list[UserInterest]
    by_category: dict[str, int]
    by_status: dict[str, int]
    matching_count: int


async def read_interest_management_page(
    db: AsyncSession,
    actor_id: UUID,
    *,
    limit: int,
    category: str | None = None,
    status: str | None = None,
    interest_id: UUID | None = None,
    after_id: UUID | None = None,
) -> InterestManagementPage:
    categories = (
        select(UserInterest.category.label("key"), func.count().label("count"))
        .where(UserInterest.user_id == actor_id)
        .group_by(UserInterest.category)
        .cte("interest_categories")
    )
    statuses = (
        select(UserInterest.status.label("key"), func.count().label("count"))
        .where(UserInterest.user_id == actor_id)
        .group_by(UserInterest.status)
        .cte("interest_statuses")
    )
    category_counts = select(
        func.coalesce(
            func.jsonb_object_agg(categories.c.key, categories.c.count), literal({}, type_=JSONB)
        )
    ).scalar_subquery()
    status_counts = select(
        func.coalesce(
            func.jsonb_object_agg(statuses.c.key, statuses.c.count), literal({}, type_=JSONB)
        )
    ).scalar_subquery()
    conditions = [UserInterest.user_id == actor_id]
    if category is not None:
        conditions.append(UserInterest.category == category)
    if status is not None:
        conditions.append(UserInterest.status == status)
    if interest_id is not None:
        conditions.append(UserInterest.id == interest_id)
    matching_count = (
        select(func.count()).select_from(UserInterest).where(*conditions).scalar_subquery()
    )
    metadata = select(
        category_counts.label("by_category"),
        status_counts.label("by_status"),
        matching_count.label("matching_count"),
    ).subquery()
    anchor = aliased(UserInterest)
    anchor_time = (
        select(anchor.created_at)
        .where(anchor.user_id == actor_id, anchor.id == after_id)
        .scalar_subquery()
    )
    selection = select(UserInterest.id).where(*conditions)
    if after_id is not None:
        selection = selection.where(
            tuple_(UserInterest.created_at, UserInterest.id)
            < tuple_(anchor_time, literal(after_id))
        )
    page = (
        selection.order_by(UserInterest.created_at.desc(), UserInterest.id.desc())
        .limit(limit + 1)
        .cte("interest_page")
    )
    statement = (
        select(
            UserInterest,
            metadata.c.by_category,
            metadata.c.by_status,
            metadata.c.matching_count,
            anchor_time,
        )
        .options(defer(UserInterest.embedding))
        .select_from(metadata)
        .outerjoin(UserInterest, UserInterest.id.in_(select(page.c.id)))
        .order_by(UserInterest.created_at.desc(), UserInterest.id.desc())
        .execution_options(populate_existing=True)
    )
    result: Result[tuple[UserInterest | None, object, object, int, datetime | None]] = (
        await db.execute(statement)
    )
    rows = result.all()
    if after_id is not None and rows[0][4] is None:
        raise ResourceNotFoundError("interest cursor", str(after_id))
    return InterestManagementPage(
        rows=[row[0] for row in rows if row[0] is not None],
        by_category=_COUNTS.validate_python(rows[0][1]),
        by_status=_COUNTS.validate_python(rows[0][2]),
        matching_count=rows[0][3],
    )
