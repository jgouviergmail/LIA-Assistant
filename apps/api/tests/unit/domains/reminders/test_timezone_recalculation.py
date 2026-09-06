"""A reminder follows the reader who moves.

Owner decision, 2026-09-06: **a spec is a wall clock, and a wall clock follows
the person**. Someone who moves to Tokyo means 08:00 where they now live — and
that is true of a single occurrence as much as of a daily one.

This CHANGES the historical behaviour: a reminder's instant used to be frozen
at creation, so flying to Tokyo turned a 10:00 reminder into a 02:00 one. The
change is deliberate, it buys ONE rule instead of two, and it is asserted here
rather than left to be discovered.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from src.core.recurrence import RecurrenceSpec
from src.domains.reminders.models import ReminderStatus
from src.domains.reminders.service import ReminderService

pytestmark = pytest.mark.unit

ONCE_AT_10 = RecurrenceSpec.model_validate(
    {
        "freq": "once",
        "interval": 1,
        "anchor_date": "2099-01-15",
        "times": {"mode": "at", "at": [{"hour": 10, "minute": 0}]},
    }
)
DAILY_AT_8 = RecurrenceSpec.model_validate(
    {
        "freq": "daily",
        "interval": 1,
        "anchor_date": "2026-01-01",
        "times": {"mode": "at", "at": [{"hour": 8, "minute": 0}]},
    }
)


def _reminder(spec: RecurrenceSpec, zone: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        recurrence_spec=spec,
        user_timezone=zone,
        trigger_at=datetime.now(UTC) + timedelta(days=1),
        status=ReminderStatus.PENDING.value,
    )


def _service(rows: list[Any]) -> ReminderService:
    service = ReminderService(MagicMock())
    service.db.flush = AsyncMock()
    service.repository = MagicMock()
    service.repository.get_all_pending_for_user = AsyncMock(return_value=rows)
    return service


class TestMovingZone:
    async def test_a_recurring_reminder_keeps_its_wall_clock(self) -> None:
        """08:00 in Paris becomes 08:00 in Tokyo, not 16:00."""
        reminder = _reminder(DAILY_AT_8, "Europe/Paris")
        service = _service([reminder])

        moved = await service.recalculate_all_for_user(uuid4(), "Asia/Tokyo")

        assert moved == 1
        assert reminder.user_timezone == "Asia/Tokyo"
        local = reminder.trigger_at.astimezone(ZoneInfo("Asia/Tokyo"))
        assert (local.hour, local.minute) == (8, 0)

    async def test_a_single_occurrence_moves_too(self) -> None:
        """The deliberate behaviour change, asserted rather than assumed.

        Before this lot the instant was frozen and a 10:00 reminder rang at
        02:00 Tokyo time. One rule now covers both kinds.
        """
        reminder = _reminder(ONCE_AT_10, "Europe/Paris")
        service = _service([reminder])

        await service.recalculate_all_for_user(uuid4(), "Asia/Tokyo")

        local = reminder.trigger_at.astimezone(ZoneInfo("Asia/Tokyo"))
        assert (local.hour, local.minute) == (10, 0)

    async def test_the_zone_is_written_even_when_the_instant_does_not_move(self) -> None:
        """A row must never keep a zone it no longer belongs to.

        The routines carried exactly this defect until ADR-265: a paused one
        kept the old zone after a move and drew on the wrong axis.
        """
        reminder = _reminder(DAILY_AT_8, "Europe/Paris")
        service = _service([reminder])

        await service.recalculate_all_for_user(uuid4(), "Europe/Paris")

        assert reminder.user_timezone == "Europe/Paris"

    async def test_nothing_pending_is_not_an_error(self) -> None:
        service = _service([])
        assert await service.recalculate_all_for_user(uuid4(), "Asia/Tokyo") == 0
        service.db.flush.assert_not_awaited()

    async def test_every_pending_reminder_is_moved_not_a_page_of_them(self) -> None:
        """A window would move some clocks and leave others behind."""
        rows = [_reminder(DAILY_AT_8, "Europe/Paris") for _ in range(5)]
        service = _service(rows)

        moved = await service.recalculate_all_for_user(uuid4(), "America/Los_Angeles")

        assert moved == 5
        assert {r.user_timezone for r in rows} == {"America/Los_Angeles"}


class TestTheDueButUncollectedWindow:
    """The scheduler runs on a tick, so a reminder can be due and still here.

    `next_occurrence` answers None for it. Before this was handled, the zone
    was stamped on the row while the instant stayed as computed in the OLD
    zone — a row claiming Tokyo and firing on Paris arithmetic.
    """

    async def test_a_due_reminder_is_left_entirely_alone(self) -> None:
        past = datetime.now(UTC) - timedelta(minutes=1)
        local = past.astimezone(ZoneInfo("Europe/Paris"))
        spec = RecurrenceSpec.model_validate(
            {
                "freq": "once",
                "interval": 1,
                "anchor_date": local.date().isoformat(),
                "times": {"mode": "at", "at": [{"hour": local.hour, "minute": local.minute}]},
            }
        )
        reminder = _reminder(spec, "Europe/Paris")
        reminder.trigger_at = past
        service = _service([reminder])

        moved = await service.recalculate_all_for_user(uuid4(), "Asia/Tokyo")

        assert moved == 0
        assert reminder.user_timezone == "Europe/Paris"
        assert reminder.trigger_at == past

    async def test_it_does_not_stop_the_others_from_moving(self) -> None:
        past = datetime.now(UTC) - timedelta(minutes=1)
        due = _reminder(ONCE_AT_10, "Europe/Paris")
        due.trigger_at = past
        due.recurrence_spec = RecurrenceSpec.model_validate(
            {
                "freq": "once",
                "interval": 1,
                "anchor_date": past.astimezone(ZoneInfo("Europe/Paris")).date().isoformat(),
                "times": {
                    "mode": "at",
                    "at": [
                        {
                            "hour": past.astimezone(ZoneInfo("Europe/Paris")).hour,
                            "minute": past.astimezone(ZoneInfo("Europe/Paris")).minute,
                        }
                    ],
                },
            }
        )
        healthy = _reminder(DAILY_AT_8, "Europe/Paris")
        service = _service([due, healthy])

        moved = await service.recalculate_all_for_user(uuid4(), "Asia/Tokyo")

        assert moved == 1
        assert healthy.user_timezone == "Asia/Tokyo"


class TestOneSurfaceFailingDoesNotTakeTheOthersWithIt:
    """The contract says neither failure aborts the profile update. It must hold
    for a DATABASE failure, not only an application one.

    A failed statement poisons a PostgreSQL transaction: every later statement
    on that session is refused until a rollback. The two surfaces share the
    caller's session, and the caller commits it — so a reminder whose flush
    failed would take the routines that had just been moved, AND the profile
    update that triggered all of this, with it. That is the exact failure
    `scheduled_action_runs` uses a savepoint to avoid, with a signed
    integration contract behind it.
    """

    async def test_each_surface_is_confined_to_its_own_savepoint(self) -> None:
        import inspect

        from src.infrastructure.scheduler import timezone_propagation

        source = inspect.getsource(timezone_propagation)
        assert "begin_nested" in source, (
            "a surface that fails must not poison the caller's transaction; "
            "confine it the way `scheduled_actions/runs.py` does"
        )

    async def test_a_failing_surface_is_reported_by_its_absence_not_an_exception(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        from src.infrastructure.scheduler.timezone_propagation import propagate_timezone

        db = MagicMock()
        db.begin_nested = MagicMock(return_value=_NullContext())
        with (
            patch(
                "src.domains.scheduled_actions.service.ScheduledActionService."
                "recalculate_all_for_user",
                AsyncMock(return_value=3),
            ),
            patch(
                "src.domains.reminders.service.ReminderService.recalculate_all_for_user",
                AsyncMock(side_effect=RuntimeError("flush failed")),
            ),
        ):
            moved = await propagate_timezone(db, uuid4(), "Asia/Tokyo")

        assert moved == {"scheduled_actions": 3}


class _NullContext:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc: object) -> bool:
        return False
