"""Reading the reminders that have not fired yet.

The domain deliberately had no listing surface: a reminder is a temporary
post-it, created by conversation and DELETED once notified
(`reminder_notification.py` — there is no "sent" state to list). That design
stands for everything it forbids: no editing, no snoozing, no acknowledgement.

What the notifications hub adds is strictly a READ. It shows the reminders that
are still coming, so the reader can see them next to everything else LIA holds
for them — and cancel one, which the card already allowed.

Because a fired reminder is gone, this section can never be a history. It lists
the FUTURE, and the interface says so rather than letting a reader look for
what they were notified of.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.reminders.models import Reminder, ReminderStatus
from src.domains.reminders.router import list_pending_reminders

pytestmark = pytest.mark.unit


def _reminder(minutes: int) -> Reminder:
    reminder = Reminder(
        user_id=uuid.uuid4(),
        content=f"Appeler le plombier ({minutes})",
        trigger_at=datetime(2026, 8, 4, 9, 0, tzinfo=UTC) + timedelta(minutes=minutes),
        status=ReminderStatus.PENDING.value,
    )
    reminder.id = uuid.uuid4()
    return reminder


async def _call(*, rows: list[Reminder], total: int, limit: int = 10, offset: int = 0):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.timezone = "Europe/Paris"
    with patch("src.domains.reminders.router.ReminderService") as service_cls:
        service_cls.return_value.list_pending_page = AsyncMock(return_value=(rows, total))
        page = await list_pending_reminders(limit=limit, offset=offset, user=user, db=AsyncMock())
        return page, service_cls.return_value, user


class TestThePendingRemindersPage:
    async def test_it_states_the_exact_total_behind_the_page(self) -> None:
        page, _, _ = await _call(rows=[_reminder(i) for i in range(10)], total=37)

        assert len(page.reminders) == 10
        assert page.total == 37

    async def test_the_window_reaches_the_service(self) -> None:
        _, service, user = await _call(rows=[], total=0, limit=25, offset=50)

        service.list_pending_page.assert_awaited_once_with(user.id, limit=25, offset=50)

    async def test_it_carries_what_the_reader_needs_to_recognise_the_reminder(self) -> None:
        row = _reminder(30)
        page, _, _ = await _call(rows=[row], total=1)

        item = page.reminders[0]
        assert item.id == row.id
        assert item.content == row.content
        assert item.trigger_at == row.trigger_at

    async def test_an_empty_list_states_zero_rather_than_omitting_the_total(self) -> None:
        page, _, _ = await _call(rows=[], total=0)

        assert page.reminders == []
        assert page.total == 0


class TestTheSurfaceStaysReadOnly:
    """The listing must not become the management UI the domain refuses."""

    def test_the_router_exposes_only_a_read_and_the_existing_cancel(self) -> None:
        from src.domains.reminders.router import router

        verbs = {(route.path, method) for route in router.routes for method in route.methods}  # type: ignore[attr-defined]

        assert ("/reminders", "GET") in verbs
        assert ("/reminders/{reminder_id}", "DELETE") in verbs
        # No edit, no snooze, no acknowledgement — the design decision stands.
        assert not any(method in {"PATCH", "PUT", "POST"} for _, method in verbs)
