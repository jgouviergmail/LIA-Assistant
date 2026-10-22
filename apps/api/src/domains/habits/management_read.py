"""Bounded owned habit pages and complete counts; source candidates exclude every saved key."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceNotFoundError
from src.domains.habits.models import HabitStatus, UserHabit
from src.domains.habits.schemas import HabitResponse


@dataclass(frozen=True)
class HabitPage:
    rows: list[HabitResponse]
    total: int


async def read_habit_page(
    db: AsyncSession,
    actor_id: UUID,
    *,
    limit: int,
    after_id: UUID | None,
    status: HabitStatus | None = None,
    habit_id: UUID | None = None,
) -> HabitPage:
    fields = tuple(HabitResponse.model_fields)
    owned = [UserHabit.user_id == actor_id]
    if status is not None:
        owned.append(UserHabit.status == status.value)
    if habit_id is not None:
        owned.append(UserHabit.id == habit_id)
    anchor = (
        select(UserHabit.kind.label("kind"), UserHabit.key.label("key"), UserHabit.id.label("id"))
        .where(*owned, UserHabit.id == after_id)
        .cte("habit_anchor")
    )
    selection = select(*(getattr(UserHabit, field) for field in fields)).where(*owned)
    if after_id is not None:
        selection = selection.where(
            tuple_(UserHabit.kind, UserHabit.key, UserHabit.id)
            > tuple_(
                select(anchor.c.kind).scalar_subquery(),
                select(anchor.c.key).scalar_subquery(),
                literal(after_id),
            )
        )
    page = (
        selection.order_by(UserHabit.kind, UserHabit.key, UserHabit.id).limit(limit + 1).subquery()
    )
    metadata = select(
        select(func.count()).select_from(UserHabit).where(*owned).scalar_subquery().label("total"),
        select(anchor.c.id).scalar_subquery().label("anchor_id"),
    ).subquery()
    statement = (
        select(*page.c, metadata.c.total, metadata.c.anchor_id)
        .select_from(metadata)
        .outerjoin(page, literal(True))
        .order_by(page.c.kind, page.c.key, page.c.id)
    )
    result = (await db.execute(statement)).mappings().all()
    if after_id is not None and result[0]["anchor_id"] is None:
        raise ResourceNotFoundError("habit cursor", after_id)
    rows = [
        HabitResponse.model_validate({field: row[field] for field in fields})
        for row in result
        if row["id"] is not None
    ]
    return HabitPage(rows=rows, total=result[0]["total"])


async def owned_habit_keys(db: AsyncSession, actor_id: UUID) -> set[str]:
    """Only keys enter the existing advisory candidate exclusion set, never full payloads."""
    return set((await db.scalars(select(UserHabit.key).where(UserHabit.user_id == actor_id))).all())
