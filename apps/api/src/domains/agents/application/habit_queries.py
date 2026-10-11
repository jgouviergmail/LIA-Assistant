"""Reading learned records neither learns nor recomputes nor records human presence."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.core.time_utils import resolve_user_timezone
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.habit_read_schemas import HabitRead, HabitsProjection
from src.domains.habits.candidates import list_recurrence_candidates
from src.domains.habits.management_read import owned_habit_keys, read_habit_page
from src.domains.habits.overview_projection import build_overview_response
from src.domains.habits.service import HabitsService
from src.domains.users.models import User


async def require_habit_records(db: AsyncSession, actor_id: UUID) -> User:
    await require_application_tools(db)
    if not settings.habits_enabled:
        raise AuthorizationError(detail={"error_code": "CAPABILITY_DISABLED"})
    return await load_actor(db, actor_id)


async def read_habits(db: AsyncSession, actor_id: UUID, query: HabitRead) -> HabitsProjection:
    selected = HabitRead.model_validate(query.model_dump())
    actor = await require_habit_records(db, actor_id)
    timezone = resolve_user_timezone(actor)
    today = datetime.now(timezone).date()
    page = await read_habit_page(db, actor_id, limit=selected.limit, after_id=selected.after_id)
    service = HabitsService(db)
    profile = await service.repository.get_profile(actor_id)
    streak = await service.get_streaks(actor_id, today=today)
    candidates, candidates_more = await list_recurrence_candidates(
        actor_id,
        local_today=today,
        exclude_keys=await owned_habit_keys(db, actor_id),
        settings=settings,
        limit=settings.habits_candidates_display_max,
    )
    rows, more = page.rows[: selected.limit], len(page.rows) > selected.limit
    source = build_overview_response(actor, profile, streak, rows, candidates, candidates_more)
    refreshed = await require_habit_records(db, actor_id)
    if (
        refreshed.habits_enabled != source.habits_enabled
        or resolve_user_timezone(refreshed) != timezone
    ):
        raise ValueError("Habit preferences changed while reading; retry the observation")
    return HabitsProjection.model_validate(
        {
            **source.model_dump(mode="json"),
            "total": page.total,
            "returned_count": len(rows),
            "truncated": more,
            "next_cursor": rows[-1].id if more else None,
            "timezone": str(timezone),
            "observed_at": datetime.now(UTC),
        }
    )
