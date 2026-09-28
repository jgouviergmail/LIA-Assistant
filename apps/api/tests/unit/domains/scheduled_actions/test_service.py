"""``ScheduledActionService`` against a repository double.

The first unit suite of the service: until ADR-265 its behaviour was only
exercised through the router and the users service. What it pins is the
timezone move — a paused routine must follow the user's zone like an active
one, because re-enabling and editing both re-derive the trigger from the
stored ``user_timezone``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.exceptions import ValidationError
from src.core.recurrence import DailyTimes, RecurrenceSpec, SeriesEnd, TimeOfDay
from src.domains.scheduled_actions.models import ScheduledActionStatus
from src.domains.scheduled_actions.schemas import (
    ConditionConfig,
    ScheduledActionCreate,
    ScheduledActionUpdate,
)
from src.domains.scheduled_actions.service import ScheduledActionService
from src.domains.scheduled_actions.trigger import TriggerPlan, check_interval

pytestmark = pytest.mark.unit

PARIS_MORNING = datetime(2026, 8, 3, 6, 0, tzinfo=UTC)  # 08:00 Paris


_EVERY_DAY_AT_EIGHT = RecurrenceSpec(
    freq="weekly",
    times=DailyTimes(mode="at", at=(TimeOfDay(hour=8, minute=0),)),
    anchor_date=date(2026, 1, 5),
    byweekday=(1, 2, 3, 4, 5, 6, 7),
)


def _action(**over: Any) -> SimpleNamespace:
    base = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "recurrence": _EVERY_DAY_AT_EIGHT.model_dump(mode="json"),
        "recurrence_spec": _EVERY_DAY_AT_EIGHT,
        "trigger_kind": "time",
        "condition_config": None,
        "condition_state": None,
        "user_timezone": "Europe/Paris",
        "is_enabled": True,
        "next_trigger_at": PARIS_MORNING,
        "status": "active",
        "consecutive_failures": 0,
        "last_error": None,
    }
    base.update(over)
    return SimpleNamespace(**base)


def _editing(action: SimpleNamespace) -> ScheduledActionService:
    """A service whose repository serves the row and writes straight onto it.

    The ownership check is the service's own: the caller passes the row's
    ``user_id``, as the router does.
    """

    def _apply(row: SimpleNamespace, data: dict[str, Any]) -> SimpleNamespace:
        for key, value in data.items():
            setattr(row, key, value)
        return row

    service = ScheduledActionService(MagicMock())
    service.repository = MagicMock()
    service.repository.get_by_id = AsyncMock(return_value=action)
    service.repository.update = AsyncMock(side_effect=_apply)
    return service


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

        repo.get_by_id = AsyncMock(return_value=paused)
        repo.update = AsyncMock(side_effect=_update)
        toggled = await service.toggle(paused.id, paused.user_id)

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
            "condition_state": None,
        }
        base.update(over)
        return SimpleNamespace(**base)

    async def test_a_new_schedule_puts_a_closed_routine_back_to_work(self) -> None:
        action = self._closed()
        service = _editing(action)

        await service.update(action.id, action.user_id, ScheduledActionUpdate(recurrence=_LIVE))

        assert action.is_enabled is True
        assert action.status == ScheduledActionStatus.ACTIVE.value
        assert action.next_trigger_at is not None

    async def test_a_routine_the_person_paused_stays_paused(self) -> None:
        """A pause is a decision; editing the schedule does not undo it."""
        action = self._closed(status=ScheduledActionStatus.ACTIVE.value)
        service = _editing(action)

        await service.update(action.id, action.user_id, ScheduledActionUpdate(recurrence=_LIVE))

        assert action.is_enabled is False
        assert action.status == ScheduledActionStatus.ACTIVE.value

    async def test_an_edit_that_leaves_the_series_over_changes_nothing(self) -> None:
        """No future, no revival: reopening would promise a run it does not have."""
        action = self._closed(recurrence=_OVER.model_dump(mode="json"), recurrence_spec=_OVER)
        service = _editing(action)

        await service.update(action.id, action.user_id, ScheduledActionUpdate(recurrence=_OVER))

        assert action.is_enabled is False
        assert action.status == ScheduledActionStatus.COMPLETED.value
        assert action.next_trigger_at is None

    async def test_an_edit_that_does_not_touch_the_schedule_leaves_it_closed(self) -> None:
        action = self._closed()
        service = _editing(action)

        await service.update(action.id, action.user_id, ScheduledActionUpdate(title="Autre"))

        assert action.is_enabled is False
        assert action.status == ScheduledActionStatus.COMPLETED.value

    async def test_an_active_routine_is_not_touched_by_the_rule(self) -> None:
        action = self._closed(is_enabled=True, status=ScheduledActionStatus.ACTIVE.value)
        service = _editing(action)

        await service.update(action.id, action.user_id, ScheduledActionUpdate(recurrence=_LIVE))

        assert action.is_enabled is True
        assert action.status == ScheduledActionStatus.ACTIVE.value


# =============================================================================
# One clock per routine (ADR-322)
# =============================================================================


def _watch(**over: Any) -> SimpleNamespace:
    """A condition routine as the ORM hands it over."""
    base: dict[str, Any] = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "recurrence": None,
        "recurrence_spec": None,
        "trigger_kind": "condition",
        "condition_config": {"type": "mail_match", "query": "devis"},
        "condition_state": {"seen": ["k1"], "last_checked_at": None},
        "user_timezone": "Europe/Paris",
        "is_enabled": True,
        "status": ScheduledActionStatus.ACTIVE.value,
        "next_trigger_at": PARIS_MORNING,
        "consecutive_failures": 0,
        "last_error": None,
    }
    base.update(over)
    return SimpleNamespace(**base)


class TestCreatingAWatch:
    async def test_it_stores_no_schedule_and_arms_its_first_check(self) -> None:
        service = ScheduledActionService(MagicMock())
        service.repository = MagicMock()
        service.repository.count_for_user = AsyncMock(return_value=0)
        service.repository.create = AsyncMock(side_effect=lambda data: SimpleNamespace(**data))
        before = datetime.now(UTC)

        created = await service.create(
            uuid.uuid4(),
            ScheduledActionCreate(
                title="Devis",
                action_prompt="préviens-moi",
                trigger_kind="condition",
                condition_config=ConditionConfig(
                    type="mail_match", query="devis", until=date(2099, 1, 1)
                ),
            ),
            "Europe/Paris",
        )

        assert created.recurrence is None
        assert created.condition_config == {
            "type": "mail_match",
            "query": "devis",
            "until": "2099-01-01",
        }
        # The first check within one cadence, on the routine's own phase.
        assert before < created.next_trigger_at <= before + timedelta(minutes=16)
        assert created.next_trigger_at == TriggerPlan.of(
            SimpleNamespace(**{**created.__dict__, "recurrence_spec": None})
        ).first(before)

    async def test_a_last_day_already_over_is_refused(self) -> None:
        service = ScheduledActionService(MagicMock())
        service.repository = MagicMock()
        service.repository.count_for_user = AsyncMock(return_value=0)

        with pytest.raises(ValidationError, match="until"):
            await service.create(
                uuid.uuid4(),
                ScheduledActionCreate(
                    title="Devis",
                    action_prompt="préviens-moi",
                    trigger_kind="condition",
                    condition_config=ConditionConfig(type="task_overdue", until=date(2020, 1, 1)),
                ),
                "Europe/Paris",
            )


class TestSwitchingClocks:
    async def test_becoming_a_watch_drops_the_schedule(self) -> None:
        action = _action(condition_state=None)
        service = _editing(action)

        await service.update(
            action.id,
            action.user_id,
            ScheduledActionUpdate(
                trigger_kind="condition", condition_config=ConditionConfig(type="task_overdue")
            ),
        )

        assert action.recurrence is None
        assert action.trigger_kind == "condition"
        assert action.condition_config == {"type": "task_overdue"}
        assert action.condition_state is None
        # Armed on its first check: within one published interval.
        assert action.next_trigger_at <= datetime.now(UTC) + check_interval("task_overdue")

    async def test_a_watch_sent_with_a_schedule_is_refused(self) -> None:
        action = _action()
        service = _editing(action)

        with pytest.raises(ValidationError, match="no recurrence"):
            await service.update(
                action.id,
                action.user_id,
                ScheduledActionUpdate(
                    trigger_kind="condition",
                    condition_config=ConditionConfig(type="task_overdue"),
                    recurrence=_EVERY_DAY_AT_EIGHT,
                ),
            )

    async def test_becoming_scheduled_needs_a_schedule(self) -> None:
        action = _watch()
        service = _editing(action)

        with pytest.raises(ValidationError, match="recurrence is required"):
            await service.update(
                action.id, action.user_id, ScheduledActionUpdate(trigger_kind="time")
            )

    async def test_becoming_scheduled_drops_the_condition_and_its_ledger(self) -> None:
        action = _watch()
        service = _editing(action)

        await service.update(
            action.id,
            action.user_id,
            ScheduledActionUpdate(trigger_kind="time", recurrence=_EVERY_DAY_AT_EIGHT),
        )

        assert action.condition_config is None
        assert action.condition_state is None
        assert action.recurrence == _EVERY_DAY_AT_EIGHT.model_dump(mode="json")
        local = action.next_trigger_at.astimezone(__import__("zoneinfo").ZoneInfo("Europe/Paris"))
        assert (local.hour, local.minute) == (8, 0)


class TestEditingAWatch:
    async def test_moving_its_last_day_keeps_what_it_has_seen(self) -> None:
        # The same facts watched a little longer: nothing becomes new again.
        action = _watch()
        service = _editing(action)

        await service.update(
            action.id,
            action.user_id,
            ScheduledActionUpdate(
                condition_config=ConditionConfig(
                    type="mail_match", query="devis", until=date(2099, 1, 1)
                )
            ),
        )

        assert action.condition_state == {"seen": ["k1"], "last_checked_at": None}
        assert action.condition_config["until"] == "2099-01-01"

    async def test_watching_something_else_starts_a_fresh_ledger(self) -> None:
        action = _watch()
        service = _editing(action)

        await service.update(
            action.id,
            action.user_id,
            ScheduledActionUpdate(
                condition_config=ConditionConfig(type="mail_match", query="facture")
            ),
        )

        assert action.condition_state is None

    async def test_renaming_a_finished_watch_is_not_refused_for_its_past_day(self) -> None:
        action = _watch(
            condition_config={"type": "task_overdue", "until": "2020-01-01"},
            is_enabled=False,
            status=ScheduledActionStatus.COMPLETED.value,
            next_trigger_at=None,
        )
        service = _editing(action)

        await service.update(action.id, action.user_id, ScheduledActionUpdate(title="Archive"))

        assert action.title == "Archive"
        assert action.status == ScheduledActionStatus.COMPLETED.value

    async def test_giving_a_finished_watch_a_new_last_day_puts_it_back_to_work(self) -> None:
        action = _watch(
            condition_config={"type": "task_overdue", "until": "2020-01-01"},
            is_enabled=False,
            status=ScheduledActionStatus.COMPLETED.value,
            next_trigger_at=None,
        )
        service = _editing(action)

        await service.update(
            action.id,
            action.user_id,
            ScheduledActionUpdate(
                condition_config=ConditionConfig(type="task_overdue", until=date(2099, 1, 1))
            ),
        )

        assert action.is_enabled is True
        assert action.status == ScheduledActionStatus.ACTIVE.value
        assert action.next_trigger_at is not None

    async def test_setting_a_last_day_already_over_is_refused(self) -> None:
        action = _watch()
        service = _editing(action)

        with pytest.raises(ValidationError, match="until"):
            await service.update(
                action.id,
                action.user_id,
                ScheduledActionUpdate(
                    condition_config=ConditionConfig(
                        type="mail_match", query="devis", until=date(2020, 1, 1)
                    )
                ),
            )


class TestAWatchOnTheSystemsClock:
    async def test_re_enabling_arms_the_next_check(self) -> None:
        action = _watch(is_enabled=False, next_trigger_at=None)
        service = _editing(action)

        toggled = await service.toggle(action.id, action.user_id)

        assert toggled.is_enabled is True
        assert (
            datetime.now(UTC) < toggled.next_trigger_at <= datetime.now(UTC) + timedelta(minutes=16)
        )

    async def test_moving_reads_the_last_day_in_the_new_zone(self) -> None:
        # 00:30 on the 26th in Paris is 18:30 on the 25th in New York: a watch
        # « until the 25th » that just ended in Paris still runs after the move.
        watch = _watch(condition_config={"type": "task_overdue", "until": "2026-09-25"})
        service, repo = _service([watch])
        late = datetime(2026, 9, 25, 22, 30, tzinfo=UTC)

        with patch("src.domains.scheduled_actions.service.now_utc", return_value=late):
            await service.recalculate_all_for_user(uuid.uuid4(), "America/New_York")

        recalculated = repo.update_timezone_for_user.await_args.kwargs["recalculated_triggers"]
        assert recalculated[watch.id] is not None
        assert recalculated[watch.id] < datetime(2026, 9, 26, 4, 0, tzinfo=UTC)
        # Left in Paris, the same watch would have nothing left.
        assert TriggerPlan.of(watch).first(late) is None
