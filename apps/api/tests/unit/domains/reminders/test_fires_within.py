"""Which pending reminders fire within a window — « do I have a reminder that day? ».

A reminder keeps only its NEXT instant in ``trigger_at``; its schedule says the
rest (ADR-268, one engine). A daily reminder due tomorrow fires the day after
too, which a filter on ``trigger_at`` alone would miss. A one-shot reminder is
``freq='once'``, so no branch asks « is it recurring »: every reminder is read
through the engine, from its next instant on.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from src.core.recurrence.spec import RecurrenceSpec
from src.domains.reminders.models import Reminder, ReminderStatus
from src.domains.reminders.service import ReminderService, fires_within

pytestmark = pytest.mark.unit

PARIS = ZoneInfo("Europe/Paris")
#: Tuesday 17 November 2026, a whole day in Paris.
TUESDAY = (datetime(2026, 11, 17, tzinfo=PARIS), datetime(2026, 11, 18, tzinfo=PARIS))


def _reminder(trigger_at: datetime, recurrence: dict[str, object]) -> Reminder:
    reminder = Reminder(
        user_id=uuid.uuid4(),
        content="Rapporter les livres",
        trigger_at=trigger_at,
        recurrence=recurrence,
        user_timezone="Europe/Paris",
        status=ReminderStatus.PENDING.value,
    )
    reminder.id = uuid.uuid4()
    return reminder


def _once(at: datetime) -> Reminder:
    local = at.astimezone(PARIS)
    spec = RecurrenceSpec.model_validate(
        {
            "freq": "once",
            "anchor_date": local.date().isoformat(),
            "times": {"at": [{"hour": local.hour, "minute": local.minute}]},
        }
    )
    return _reminder(at, spec.model_dump(mode="json"))


def _daily_at_eight(next_at: datetime, *, weekdays: list[int] | None = None) -> Reminder:
    rule: dict[str, object] = {
        "freq": "weekly" if weekdays else "daily",
        "anchor_date": "2026-11-01",
        "times": {"at": [{"hour": 8, "minute": 0}]},
    }
    if weekdays:
        rule["byweekday"] = weekdays
    spec = RecurrenceSpec.model_validate(rule)
    return _reminder(next_at, spec.model_dump(mode="json"))


def test_a_one_shot_reminder_fires_on_its_own_day_only() -> None:
    reminder = _once(datetime(2026, 11, 17, 9, tzinfo=UTC))

    assert fires_within(reminder, *TUESDAY)
    assert not fires_within(
        reminder, datetime(2026, 11, 18, tzinfo=PARIS), datetime(2026, 11, 19, tzinfo=PARIS)
    )


def test_a_daily_reminder_due_the_day_before_fires_that_day_too() -> None:
    """Its ``trigger_at`` is Monday's; Tuesday is in its schedule."""
    assert fires_within(_daily_at_eight(datetime(2026, 11, 16, 7, tzinfo=UTC)), *TUESDAY)


def test_a_weekly_reminder_fires_only_on_its_weekdays() -> None:
    """Mondays only (ISO 1): nothing on a Tuesday."""
    reminder = _daily_at_eight(datetime(2026, 11, 16, 7, tzinfo=UTC), weekdays=[1])

    assert not fires_within(reminder, *TUESDAY)


def test_an_instant_already_past_its_next_firing_is_not_counted_again() -> None:
    """An occurrence before ``trigger_at`` has fired: the pending reminder is the next."""
    reminder = _daily_at_eight(datetime(2026, 11, 18, 7, tzinfo=UTC))

    assert not fires_within(reminder, *TUESDAY)


def test_a_schedule_it_cannot_read_falls_back_on_the_next_instant() -> None:
    """One malformed stored schedule must not hide a reminder due that day."""
    reminder = _reminder(datetime(2026, 11, 17, 9, tzinfo=UTC), {"freq": "not a frequency"})

    assert fires_within(reminder, *TUESDAY)


async def test_the_service_reads_every_page_due_before_the_window_s_end() -> None:
    """The bounded page the agents list is no limit on the day's reminders."""
    due = _once(datetime(2026, 11, 17, 9, tzinfo=UTC))
    earlier = [_once(datetime(2026, 11, 16, 9, tzinfo=UTC)) for _ in range(3)]
    repository = MagicMock()
    repository.get_pending_for_user = AsyncMock(side_effect=[[*earlier[:2]], [earlier[2], due], []])
    service = ReminderService.__new__(ReminderService)
    service.repository = repository

    found = await service.list_pending_for_user(uuid.uuid4(), fires_between=TUESDAY, page_size=2)

    assert found == [due]
    assert all(
        call.kwargs["firing_before"] == TUESDAY[1]
        for call in repository.get_pending_for_user.await_args_list
    )
