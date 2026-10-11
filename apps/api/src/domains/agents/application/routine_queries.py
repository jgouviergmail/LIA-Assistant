"""Read owned Studio data; computed schedules and private-ledger exclusions remain source-owned."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.routine_read_schemas import RoutineProjection, RoutineRead
from src.domains.scheduled_actions.schemas import (
    ScheduledActionListResponse,
    ScheduledActionResponse,
)
from src.domains.scheduled_actions.service import ScheduledActionService
from src.domains.scheduled_actions.week_projection import project_routine_week


async def read_routines(
    db: AsyncSession, actor_id: UUID, request: RoutineRead
) -> RoutineProjection:
    selected = RoutineRead.model_validate(request.model_dump())
    await require_application_tools(db)
    await load_actor(db, actor_id)
    source = ScheduledActionService(db)
    owned = (
        await source.get_with_ownership_check(selected.routine_id, actor_id)
        if selected.routine_id
        else None
    )
    page = (
        [owned]
        if owned is not None
        else await source.repository.page_for_user(
            actor_id, after_id=selected.after_id, limit=selected.limit
        )
    )
    has_more = len(page) > selected.limit
    rows = page[: selected.limit]
    total = 1 if owned is not None else await source.repository.count_for_user(actor_id)
    cursor = rows[-1].id if has_more else None
    if selected.view == "week":
        weeks = await source.week_for_user(actor_id, action_ids=[row.id for row in rows])
        by_id = {week.action_id: week for week in weeks}
        weeks = [by_id[row.id] for row in rows if row.id in by_id]
        result = RoutineProjection(
            view="week",
            week=project_routine_week(weeks),
            returned_count=len(weeks),
            total_available=total,
            truncated=has_more,
            next_cursor=cursor,
        )
    else:
        result = RoutineProjection(
            view="settings",
            settings=ScheduledActionListResponse(
                scheduled_actions=[ScheduledActionResponse.model_validate(row) for row in rows],
                total=total,
            ),
            returned_count=len(rows),
            total_available=total,
            truncated=has_more,
            next_cursor=cursor,
        )
    await require_application_tools(db)
    await load_actor(db, actor_id)
    return result
