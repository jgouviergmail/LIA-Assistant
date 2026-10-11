"""One owned source explanation is shared by the UI and the native assistant."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceNotFoundError
from src.domains.habits.candidates import observed_days_for_signature
from src.domains.habits.models import HabitKind
from src.domains.habits.schemas import HabitExplanationResponse
from src.domains.habits.service import HabitsService


async def read_managed_habit_explanation(
    db: AsyncSession, actor_id: UUID, habit_id: UUID
) -> HabitExplanationResponse:
    service = HabitsService(db)
    habit = await service.repository.get_owned(habit_id, actor_id)
    if habit is None:
        raise ResourceNotFoundError("habit", str(habit_id))
    observed = (
        await observed_days_for_signature(actor_id, habit.key)
        if habit.kind == HabitKind.RECURRING_REQUEST.value
        else []
    )
    return HabitExplanationResponse(**service.build_explanation(habit), observed_days=observed)
