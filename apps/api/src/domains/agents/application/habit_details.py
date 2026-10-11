"""A native explanation requires the source record and current actor, without learning acts."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.habit_detail_schemas import (
    HabitDetailProjection,
    HabitDetailRead,
)
from src.domains.agents.application.habit_queries import require_habit_records
from src.domains.habits.management_explanation import read_managed_habit_explanation


async def read_habit_details(
    db: AsyncSession, actor_id: UUID, query: HabitDetailRead
) -> HabitDetailProjection:
    request = HabitDetailRead.model_validate(query.model_dump())
    await require_habit_records(db, actor_id)
    source = await read_managed_habit_explanation(db, actor_id, request.habit_id)
    await require_habit_records(db, actor_id)
    return HabitDetailProjection.model_validate(
        {
            **source.model_dump(mode="json"),
            "habit_id": request.habit_id,
            "observed_at": datetime.now(UTC),
        }
    )
