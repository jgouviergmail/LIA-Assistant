"""The management surface: what it accepts, what it refuses, and in what order.

The domain refused a management screen by design until 2026-09-06, when the
owner reversed that decision. These tests pin the contract that replaced it —
including the two things that decision does NOT change: a listing is never a
history, and a reminder belonging to someone else answers exactly like a
missing one.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from src.core.constants import RECURRENCE_REMINDER_LIMITS, RECURRENCE_ROUTINE_LIMITS
from src.core.recurrence import RecurrenceError, RecurrenceSpec
from src.domains.reminders.models import ReminderStatus
from src.domains.reminders.router import ReminderDetail, router
from src.domains.reminders.schemas import ReminderUpdate
from src.domains.reminders.service import ReminderService

pytestmark = pytest.mark.unit


def _spec(**over: Any) -> RecurrenceSpec:
    payload: dict[str, Any] = {
        "freq": "daily",
        "interval": 1,
        "anchor_date": "2026-09-06",
        "times": {"mode": "at", "at": [{"hour": 8, "minute": 0}]},
    }
    payload.update(over)
    return RecurrenceSpec.model_validate(payload)


def _row(spec: RecurrenceSpec | None = None, **over: Any) -> SimpleNamespace:
    spec = spec or _spec()
    base: dict[str, Any] = {
        "id": uuid4(),
        "content": "prendre les vitamines",
        "trigger_at": datetime(2026, 9, 7, 6, 0, tzinfo=UTC),
        "user_timezone": "Europe/Paris",
        "recurrence": spec.model_dump(mode="json"),
        "recurrence_spec": spec,
        "status": ReminderStatus.PENDING.value,
        "created_at": datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
    }
    base.update(over)
    return SimpleNamespace(**base)


class TestRouteOrder:
    """A literal path must be declared before every parameterised one.

    There is no `GET /reminders/{id}` today, so `/detail` is unambiguous — but
    the day someone adds one, the literal path would be swallowed in silence.
    ADR-265 paid for this lesson on `/week` and `/{action_id}`.
    """

    def test_every_literal_path_precedes_every_parameterised_one(self) -> None:
        paths = [r.path for r in router.routes]  # type: ignore[attr-defined]
        first_parameterised = next(i for i, p in enumerate(paths) if "{" in p)
        assert not any("{" not in p for p in paths[first_parameterised:]), paths


class TestTheDetailIsRenderedNotStored:
    """The sentence and the upcoming instants are computed at read time."""

    def test_it_names_the_schedule_in_the_readers_language(self) -> None:
        french = ReminderDetail.of(_row(), "fr")
        german = ReminderDetail.of(_row(), "de")

        assert french.schedule_display
        assert french.schedule_display != german.schedule_display

    def test_it_publishes_the_times_the_server_resolved(self) -> None:
        row = _row(
            _spec(times={"mode": "at", "at": [{"hour": 18, "minute": 0}, {"hour": 8, "minute": 0}]})
        )

        detail = ReminderDetail.of(row, "fr")

        # Sorted and de-duplicated by the spec, never by the browser.
        assert detail.times_of_day == ["08:00", "18:00"]
        assert detail.runs_per_day == 2

    def test_a_stepped_schedule_is_expanded_by_the_server(self) -> None:
        row = _row(
            _spec(
                times={
                    "mode": "every",
                    "step_minutes": 60,
                    "start": {"hour": 8, "minute": 0},
                    "end": {"hour": 11, "minute": 0},
                }
            )
        )

        detail = ReminderDetail.of(row, "fr")

        assert detail.times_of_day == ["08:00", "09:00", "10:00", "11:00"]
        assert detail.runs_per_day == 4


class TestTheCapIsInjected:
    """The first proof that one engine serves two callers with two ceilings."""

    def test_a_reminder_may_ask_more_of_a_day_than_a_routine(self) -> None:
        assert (
            RECURRENCE_REMINDER_LIMITS.max_times_per_day
            > RECURRENCE_ROUTINE_LIMITS.max_times_per_day
        )

    def test_a_schedule_a_routine_refuses_is_accepted_for_a_reminder(self) -> None:
        """Every 20 minutes over 8 hours: 25 firings a day."""
        spec = _spec(
            times={
                "mode": "every",
                "step_minutes": 20,
                "start": {"hour": 8, "minute": 0},
                "end": {"hour": 16, "minute": 0},
            }
        )

        with pytest.raises(RecurrenceError):
            spec.validate_against(RECURRENCE_ROUTINE_LIMITS)
        spec.validate_against(RECURRENCE_REMINDER_LIMITS)  # must not raise

    def test_the_reminder_ceiling_is_still_a_ceiling(self) -> None:
        """Every 5 minutes over 8 hours: 97 firings, past 48."""
        spec = _spec(
            times={
                "mode": "every",
                "step_minutes": 5,
                "start": {"hour": 8, "minute": 0},
                "end": {"hour": 16, "minute": 0},
            }
        )

        with pytest.raises(RecurrenceError):
            spec.validate_against(RECURRENCE_REMINDER_LIMITS)


class TestAnExplicitNullRecurrenceIsRefused:
    """An absent field leaves the schedule; a null is a mistake, not a value.

    The column is NOT NULL, so accepting it would either drop the change in
    silence or fail at flush. Neither is an answer.
    """

    def test_omitting_the_field_is_fine(self) -> None:
        assert ReminderUpdate(content="autre chose").recurrence is None

    def test_sending_it_as_null_is_refused(self) -> None:
        with pytest.raises(ValueError, match="recurrence cannot be null"):
            ReminderUpdate.model_validate({"content": "x", "recurrence": None})


class TestUpdating:
    @staticmethod
    def _service(row: SimpleNamespace) -> ReminderService:
        service = ReminderService(MagicMock())
        service.db.flush = AsyncMock()
        service.get_by_id = AsyncMock(return_value=row)  # type: ignore[method-assign]
        return service

    async def test_a_new_recurrence_rearms_from_now(self) -> None:
        """The stored instant belongs to the OLD rule.

        Keeping it would fire once more on a schedule the reader has replaced.
        """
        row = _row()
        service = self._service(row)
        previous = row.trigger_at

        await service.update_reminder(
            reminder_id=row.id,
            user_id=uuid4(),
            data=ReminderUpdate(
                recurrence=_spec(times={"mode": "at", "at": [{"hour": 21, "minute": 30}]})
            ),
            user_timezone="Europe/Paris",
        )

        assert row.trigger_at != previous
        assert row.recurrence["times"]["at"] == [{"hour": 21, "minute": 30}]

    async def test_changing_only_the_content_leaves_the_schedule_alone(self) -> None:
        row = _row()
        service = self._service(row)
        previous_trigger, previous_rule = row.trigger_at, dict(row.recurrence)

        await service.update_reminder(
            reminder_id=row.id,
            user_id=uuid4(),
            data=ReminderUpdate(content="autre chose"),
            user_timezone="Europe/Paris",
        )

        assert row.content == "autre chose"
        assert row.trigger_at == previous_trigger
        assert row.recurrence == previous_rule

    async def test_a_recurrence_with_no_future_is_refused(self) -> None:
        """A single occurrence in the past would create a row that can only
        be deleted on the next tick — a change the reader would not see."""
        row = _row()
        service = self._service(row)

        with pytest.raises(ValueError, match="no future occurrence"):
            await service.update_reminder(
                reminder_id=row.id,
                user_id=uuid4(),
                data=ReminderUpdate(
                    recurrence=RecurrenceSpec.model_validate(
                        {
                            "freq": "once",
                            "interval": 1,
                            "anchor_date": "2020-01-01",
                            "times": {"mode": "at", "at": [{"hour": 8, "minute": 0}]},
                        }
                    )
                ),
                user_timezone="Europe/Paris",
            )

    async def test_a_reminder_being_processed_cannot_be_changed(self) -> None:
        """Its notification is in flight; editing it now would race the job."""
        from src.core.exceptions import ResourceConflictError

        row = _row(status=ReminderStatus.PROCESSING.value)
        service = self._service(row)

        with pytest.raises(ResourceConflictError):
            await service.update_reminder(
                reminder_id=row.id,
                user_id=uuid4(),
                data=ReminderUpdate(content="trop tard"),
                user_timezone="Europe/Paris",
            )

    async def test_moving_a_single_instant_moves_its_derived_rule_too(self) -> None:
        """Otherwise the row would describe one time and fire at another."""
        once = RecurrenceSpec.model_validate(
            {
                "freq": "once",
                "interval": 1,
                "anchor_date": "2099-01-15",
                "times": {"mode": "at", "at": [{"hour": 8, "minute": 0}]},
            }
        )
        row = _row(once)
        service = self._service(row)

        await service.update_reminder(
            reminder_id=row.id,
            user_id=uuid4(),
            data=ReminderUpdate(trigger_at=datetime(2099, 1, 20, 17, 45)),
            user_timezone="Europe/Paris",
        )

        assert row.recurrence["anchor_date"] == "2099-01-20"
        assert row.recurrence["times"]["at"] == [{"hour": 17, "minute": 45}]


class TestOneAuthorityForWhenItFires:
    """A recurrence and an instant could contradict each other.

    Measured 2026-09-06 before this guard: a payload saying "every day at
    08:00" alongside an instant at 23:00 was accepted, and the caller's instant
    won — so the card announced 08:00, the notification arrived at 23:00, and
    only the first re-arm corrected it. Two authorities, one row.
    """

    def test_sending_both_is_refused(self) -> None:
        from src.domains.reminders.schemas import ReminderCreate

        with pytest.raises(ValueError, match="not both"):
            ReminderCreate(
                content="x",
                original_message="x",
                trigger_at=datetime(2099, 1, 15, 23, 0),
                recurrence=_spec(),
            )

    def test_sending_neither_is_refused(self) -> None:
        from src.domains.reminders.schemas import ReminderCreate

        with pytest.raises(ValueError, match="not both|either"):
            ReminderCreate(content="x", original_message="x")

    def test_a_recurrence_alone_is_accepted(self) -> None:
        from src.domains.reminders.schemas import ReminderCreate

        payload = ReminderCreate(content="x", original_message="x", recurrence=_spec())
        assert payload.trigger_at is None

    def test_an_instant_alone_is_accepted(self) -> None:
        """The chat tool's path, unchanged."""
        from src.domains.reminders.schemas import ReminderCreate

        payload = ReminderCreate(
            content="x", original_message="x", trigger_at=datetime(2099, 1, 15, 9, 0)
        )
        assert payload.recurrence is None

    async def test_the_armed_instant_is_derived_from_the_recurrence(self) -> None:
        """Not taken from the caller: the schedule is the authority."""
        from src.domains.reminders.schemas import ReminderCreate
        from src.domains.reminders.service import ReminderService

        service = ReminderService(MagicMock())
        created: dict[str, Any] = {}

        async def _create(payload: dict[str, Any]) -> Any:
            created.update(payload)
            return SimpleNamespace(id=uuid4(), **payload)

        service.repository = MagicMock()
        service.repository.create = AsyncMock(side_effect=_create)

        await service.create_reminder(
            uuid4(),
            ReminderCreate(content="x", original_message="x", recurrence=_spec()),
            "Europe/Paris",
        )

        # 08:00 in Paris, whatever the caller might have preferred.
        local = created["trigger_at"].astimezone(ZoneInfo("Europe/Paris"))
        assert (local.hour, local.minute) == (8, 0)


class TestMovingASingleInstantOnARepeatingReminder:
    """A change that silently undoes itself is worse than a refusal.

    `PATCH {"trigger_at": ...}` on a daily reminder moved the stored instant,
    and the next re-arm read the RULE and threw it away. The reader would have
    seen their change accepted and then vanish.
    """

    async def test_it_is_refused_with_a_reason(self) -> None:
        row = _row()  # daily
        service = TestUpdating._service(row)

        with pytest.raises(ValueError, match="changing its recurrence"):
            await service.update_reminder(
                reminder_id=row.id,
                user_id=uuid4(),
                data=ReminderUpdate(trigger_at=datetime(2099, 1, 20, 17, 45)),
                user_timezone="Europe/Paris",
            )

    async def test_a_single_occurrence_still_moves(self) -> None:
        """The one case where the payload means exactly one thing."""
        once = RecurrenceSpec.model_validate(
            {
                "freq": "once",
                "interval": 1,
                "anchor_date": "2099-01-15",
                "times": {"mode": "at", "at": [{"hour": 8, "minute": 0}]},
            }
        )
        row = _row(once)
        service = TestUpdating._service(row)

        await service.update_reminder(
            reminder_id=row.id,
            user_id=uuid4(),
            data=ReminderUpdate(trigger_at=datetime(2099, 1, 20, 17, 45)),
            user_timezone="Europe/Paris",
        )

        assert row.recurrence["anchor_date"] == "2099-01-20"
