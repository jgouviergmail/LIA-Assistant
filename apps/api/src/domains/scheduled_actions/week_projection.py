"""The UI and assistant serialize the same already computed week facts."""

from collections.abc import Sequence

from src.core.time_utils import now_utc
from src.domains.scheduled_actions.schemas import (
    ScheduledActionWeek,
    ScheduledActionWeekCell,
    ScheduledActionWeekResponse,
)
from src.domains.scheduled_actions.week import ActionWeek


def project_routine_week(weeks: Sequence[ActionWeek]) -> ScheduledActionWeekResponse:
    return ScheduledActionWeekResponse(
        actions=[
            ScheduledActionWeek(
                id=week.action_id,
                timezone=week.timezone,
                week_start=week.week_start,
                today=week.today,
                cells=[
                    ScheduledActionWeekCell(
                        day=cell.day,
                        date=cell.date,
                        slot_at=cell.slot_at,
                        hour=cell.hour,
                        minute=cell.minute,
                        outcome=cell.outcome,
                        run_at=cell.run_at,
                        error=cell.error,
                        manual=cell.manual,
                    )
                    for cell in week.cells
                ],
            )
            for week in weeks
        ],
        generated_at=now_utc(),
    )
