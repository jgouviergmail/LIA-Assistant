"""``ScheduledActionService`` against a repository double.

The first unit suite of the service: until ADR-265 its behaviour was only
exercised through the router and the users service. What it pins is the
timezone move — a paused routine must follow the user's zone like an active
one, because re-enabling and editing both re-derive the trigger from the
stored ``user_timezone``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.recurrence import DailyTimes, RecurrenceSpec, SeriesEnd, TimeOfDay
from src.domains.scheduled_actions.models import ScheduledActionStatus
from src.domains.scheduled_actions.schemas import ScheduledActionUpdate
from src.domains.scheduled_actions.service import ScheduledActionService

pytestmark = pytest.mark.unit

PARIS_MORNING = datetime(2026, 8, 3, 6, 0, tzinfo=UTC)  # 08:00 Paris


def _action(**over: Any) -> SimpleNamespace:
    base = {
        "id": uuid.uuid4(),
        "recurrence_spec": RecurrenceSpec(
            freq="weekly",
            times=DailyTimes(mode="at", at=(TimeOfDay(hour=8, minute=0),)),
            anchor_date=date(2026, 1, 5),
            byweekday=(1, 2, 3, 4, 5, 6, 7),
        ),
        "user_timezone": "Europe/Paris",
        "is_enabled": True,
        "next_trigger_at": PARIS_MORNING,
        "status": "active",
        "consecutive_failures": 0,
        "last_error": None,
    }
    base.update(over)
    return SimpleNamespace(**base)


def _service(actions: list[SimpleNamespace]) -> tuple[ScheduledActionService, MagicMock]:
    service = ScheduledActionService(MagicMock())
    repo = MagicMock()
    repo.get_all_for_user = AsyncMock(return_value=actions)
    repo.update_timezone_for_user = AsyncMock(
        side_effect=lambda **kw: len(kw["recalculated_triggers"])
    )
    service.repository = repo
    return service, repo


class TestTimezoneMove:
    async def test_a_paused_routine_follows_the_move_like_an_active_one(self) -> None:
        active, paused = _action(), _action(is_enabled=False)
        service, repo = _service([active, paused])

        count = await service.recalculate_all_for_user(uuid.uuid4(), "America/New_York")

        assert count == 2
        recalculated = repo.update_timezone_for_user.await_args.kwargs["recalculated_triggers"]
        assert set(recalculated) == {active.id, paused.id}
        # The same wall clock, 08:00, read on the NEW zone for both.
        for instant in recalculated.values():
            assert instant.astimezone(__import__("zoneinfo").ZoneInfo("America/New_York")).hour == 8

    async def test_nothing_to_move_writes_nothing(self) -> None:
        service, repo = _service([])
        assert await service.recalculate_all_for_user(uuid.uuid4(), "Asia/Tokyo") == 0
        repo.update_timezone_for_user.assert_not_awaited()

    async def test_re_enabling_after_a_move_wakes_up_on_the_new_zone(self) -> None:
        """The defect the move fix closes, end to end at the service level.

        Before: the paused routine kept ``Europe/Paris`` through the move, and
        ``toggle`` re-armed it from that stored zone — 08:00 Paris, i.e. 02:00
        in New York. After: the move rewrites the zone on the paused row too,
        so the re-arm reads 08:00 New York.
        """
        paused = _action(is_enabled=False)
        service, repo = _service([paused])

        async def _apply_move(**kw: Any) -> int:
            paused.user_timezone = kw["new_timezone"]
            return len(kw["recalculated_triggers"])

        repo.update_timezone_for_user = AsyncMock(side_effect=_apply_move)
        await service.recalculate_all_for_user(uuid.uuid4(), "America/New_York")

        async def _update(action: Any, data: dict[str, Any]) -> Any:
            for key, value in data.items():
                setattr(action, key, value)
            return action

        service.get_with_ownership_check = AsyncMock(return_value=paused)  # type: ignore[method-assign]
        repo.update = AsyncMock(side_effect=_update)
        toggled = await service.toggle(paused.id, uuid.uuid4())

        assert toggled.is_enabled is True
        local = toggled.next_trigger_at.astimezone(
            __import__("zoneinfo").ZoneInfo("America/New_York")
        )
        assert (local.hour, local.minute) == (8, 0)


# A series with a future, and one whose end has already passed.
_LIVE = RecurrenceSpec(
    freq="daily",
    times=DailyTimes(mode="at", at=(TimeOfDay(hour=8, minute=0),)),
    anchor_date=date(2026, 1, 5),
)
_OVER = RecurrenceSpec(
    freq="daily",
    times=DailyTimes(mode="at", at=(TimeOfDay(hour=8, minute=0),)),
    anchor_date=date(2020, 1, 1),
    end=SeriesEnd(kind="on_date", on_date=date(2020, 1, 10)),
)


class TestRevivingAClosedRoutine:
    """Extending a finished routine must actually restart it (ADR-281, lot 5).

    The executor closes a routine with no future (`is_enabled = False`,
    `status = COMPLETED`). Giving it a future again — a later `SeriesEnd`, a
    bigger `after_count` — recomputes its trigger, but the row stayed closed:
    the person edited their routine and it silently never ran again.

    The rule is about WHO closed it. The system closed a finished routine, so
    the system reopens it once the reason is gone. A PAUSE is the person's own
    decision, and an edit is not a request to resume.
    """

    @staticmethod
    def _closed(**over: Any) -> SimpleNamespace:
        base = {
            "id": uuid.uuid4(),
            "user_id": uuid.uuid4(),
            "recurrence": _LIVE.model_dump(mode="json"),
            "recurrence_spec": _LIVE,
            "user_timezone": "Europe/Paris",
            "is_enabled": False,
            "status": ScheduledActionStatus.COMPLETED.value,
            "next_trigger_at": None,
            "trigger_kind": "time",
            "condition_config": None,
        }
        base.update(over)
        return SimpleNamespace(**base)

    @staticmethod
    def _with(action: SimpleNamespace) -> ScheduledActionService:
        """A service whose repository writes straight onto the row."""

        def _apply(row: SimpleNamespace, data: dict[str, Any]) -> SimpleNamespace:
            for key, value in data.items():
                setattr(row, key, value)
            return row

        service = ScheduledActionService(MagicMock())
        service.get_with_ownership_check = AsyncMock(return_value=action)  # type: ignore[method-assign]
        service.repository = MagicMock()
        service.repository.update = AsyncMock(side_effect=_apply)
        return service

    async def test_a_new_schedule_puts_a_closed_routine_back_to_work(self) -> None:
        action = self._closed()
        service = self._with(action)

        await service.update(action.id, action.user_id, ScheduledActionUpdate(recurrence=_LIVE))

        assert action.is_enabled is True
        assert action.status == ScheduledActionStatus.ACTIVE.value
        assert action.next_trigger_at is not None

    async def test_a_routine_the_person_paused_stays_paused(self) -> None:
        """A pause is a decision; editing the schedule does not undo it."""
        action = self._closed(status=ScheduledActionStatus.ACTIVE.value)
        service = self._with(action)

        await service.update(action.id, action.user_id, ScheduledActionUpdate(recurrence=_LIVE))

        assert action.is_enabled is False
        assert action.status == ScheduledActionStatus.ACTIVE.value

    async def test_an_edit_that_leaves_the_series_over_changes_nothing(self) -> None:
        """No future, no revival: reopening would promise a run it does not have."""
        action = self._closed(recurrence=_OVER.model_dump(mode="json"), recurrence_spec=_OVER)
        service = self._with(action)

        await service.update(action.id, action.user_id, ScheduledActionUpdate(recurrence=_OVER))

        assert action.is_enabled is False
        assert action.status == ScheduledActionStatus.COMPLETED.value
        assert action.next_trigger_at is None

    async def test_an_edit_that_does_not_touch_the_schedule_leaves_it_closed(self) -> None:
        action = self._closed()
        service = self._with(action)

        await service.update(action.id, action.user_id, ScheduledActionUpdate(title="Autre"))

        assert action.is_enabled is False
        assert action.status == ScheduledActionStatus.COMPLETED.value

    async def test_an_active_routine_is_not_touched_by_the_rule(self) -> None:
        action = self._closed(is_enabled=True, status=ScheduledActionStatus.ACTIVE.value)
        service = self._with(action)

        await service.update(action.id, action.user_id, ScheduledActionUpdate(recurrence=_LIVE))

        assert action.is_enabled is True
        assert action.status == ScheduledActionStatus.ACTIVE.value
