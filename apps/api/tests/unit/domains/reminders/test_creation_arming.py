"""The confirmation clock and source writer use the same timezone and recurrence rule."""

from datetime import UTC, date, datetime

import pytest

from src.core.constants import RECURRENCE_REMINDER_LIMITS
from src.core.recurrence import DailyTimes, RecurrenceError, RecurrenceSpec, TimeOfDay
from src.domains.reminders.schemas import ReminderCreate
from src.domains.reminders.service import resolve_reminder_creation

pytestmark = pytest.mark.unit


def test_single_reminder_arming_preserves_seconds_and_uses_the_account_timezone() -> None:
    arming = resolve_reminder_creation(
        ReminderCreate(
            content="Reminder",
            original_message="Reminder",
            trigger_at=datetime(2099, 1, 15, 9, 3, 19),
        ),
        "Europe/Paris",
    )
    assert arming.trigger_at == datetime(2099, 1, 15, 8, 3, 19, tzinfo=UTC)
    assert arming.recurrence.freq == "once" and arming.recurrence.anchor_date == date(2099, 1, 15)


def test_recurrence_preview_and_source_enforce_the_reminder_ceiling() -> None:
    moments = tuple(
        TimeOfDay(hour=index // 60, minute=index % 60)
        for index in range(RECURRENCE_REMINDER_LIMITS.max_times_per_day + 1)
    )
    spec = RecurrenceSpec(
        freq="daily", times=DailyTimes(mode="at", at=moments), anchor_date=date(2099, 1, 1)
    )
    with pytest.raises(RecurrenceError):
        resolve_reminder_creation(
            ReminderCreate(content="Reminder", original_message="Reminder", recurrence=spec),
            "Europe/Paris",
        )
