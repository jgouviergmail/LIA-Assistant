"""Reminder updates preview the same source result without partial in-memory mutation."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.recurrence import RecurrenceSpec
from src.domains.reminders.models import Reminder, ReminderStatus
from src.domains.reminders.schemas import ReminderUpdate
from src.domains.reminders.service import ReminderService, once_at, preview_reminder_update

pytestmark = pytest.mark.unit


def pending() -> Reminder:
    instant = datetime(2099, 1, 2, 9, 3, 19, tzinfo=UTC)
    return Reminder(
        id=uuid4(),
        user_id=uuid4(),
        content="Before",
        original_message="Private",
        trigger_at=instant,
        user_timezone="Europe/Paris",
        status=ReminderStatus.PENDING.value,
        recurrence=once_at(instant, "Europe/Paris").model_dump(mode="json"),
    )


@pytest.mark.parametrize("change", ["content", "instant", "recurrence"])
def test_preview_is_pure_and_preserves_exact_source_schedule(change: str) -> None:
    row = pending()
    before = (row.content, row.trigger_at, row.user_timezone, row.recurrence.copy())
    new_instant = row.trigger_at + timedelta(hours=1)
    spec = RecurrenceSpec.model_validate(
        {
            "freq": "daily",
            "anchor_date": "2099-01-03",
            "times": {"mode": "at", "at": [{"hour": 10, "minute": 0}]},
        }
    )
    changes = {
        "content": ReminderUpdate(content="After"),
        "instant": ReminderUpdate(trigger_at=new_instant),
        "recurrence": ReminderUpdate(recurrence=spec),
    }
    result = preview_reminder_update(
        row, changes[change], "UTC", now=datetime(2099, 1, 3, 9, tzinfo=UTC)
    )
    assert (row.content, row.trigger_at, row.user_timezone, row.recurrence) == before
    assert result.content == ("After" if change == "content" else "Before")
    if change == "instant":
        assert result.trigger_at == new_instant and result.user_timezone == "UTC"
        assert result.recurrence == once_at(new_instant, "UTC")
    elif change == "recurrence":
        assert result.trigger_at == datetime(2099, 1, 3, 10, tzinfo=UTC)
        assert result.recurrence == spec and result.user_timezone == "UTC"
    else:
        assert result.trigger_at == row.trigger_at and result.user_timezone == "Europe/Paris"


async def test_rejected_schedule_does_not_partially_replace_the_content() -> None:
    row = pending()
    database = AsyncMock()
    service = ReminderService(database)
    service.get_by_id = AsyncMock(return_value=row)
    elapsed = RecurrenceSpec.model_validate(
        {
            "freq": "once",
            "anchor_date": "2000-01-01",
            "times": {"mode": "at", "at": [{"hour": 10, "minute": 0}]},
        }
    )
    with pytest.raises(ValueError, match="future occurrence"):
        await service.update_reminder(
            row.id, row.user_id, ReminderUpdate(content="Must not leak", recurrence=elapsed), "UTC"
        )
    assert row.content == "Before"
    database.flush.assert_not_awaited()
