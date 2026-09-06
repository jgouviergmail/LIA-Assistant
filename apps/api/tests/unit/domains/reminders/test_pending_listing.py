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


class TestWhatTheSurfaceOffers:
    """The domain gained a management screen on 2026-09-06; not everything.

    This class asserted the opposite until that day: "no edit, no snooze, no
    acknowledgement — the design decision stands". The owner reversed the
    first of those three, and it is now a first-class verb. The other two were
    never asked for and are still absent, so the assertion narrows rather than
    disappearing — a guard that only ever loosened would stop guarding.
    """

    def test_the_router_offers_reading_creating_changing_and_deleting(self) -> None:
        from src.domains.reminders.router import router

        verbs = {(route.path, method) for route in router.routes for method in route.methods}  # type: ignore[attr-defined]

        assert ("/reminders", "GET") in verbs
        assert ("/reminders/detail", "GET") in verbs
        assert ("/reminders", "POST") in verbs
        assert ("/reminders/{reminder_id}", "PATCH") in verbs
        assert ("/reminders/{reminder_id}", "DELETE") in verbs

    def test_there_is_still_no_snooze_and_no_acknowledgement(self) -> None:
        """Neither was asked for, and both would need state the row has not.

        A snooze is a schedule change (PATCH already does it); an
        acknowledgement would need a status the domain deliberately lacks,
        since a reminder with no future is deleted rather than marked.
        """
        from src.domains.reminders.router import router

        paths = {route.path for route in router.routes}  # type: ignore[attr-defined]

        assert not any("snooze" in p or "acknowledge" in p for p in paths), paths

    def test_the_listing_is_still_never_a_history(self) -> None:
        """The one thing the reversal did NOT change.

        A reminder is deleted the moment it has no future left, so there is
        nothing behind it to list. A route promising past reminders would be a
        promise the storage cannot keep.
        """
        from src.domains.reminders.router import router

        paths = {route.path for route in router.routes}  # type: ignore[attr-defined]

        assert not any("history" in p or "past" in p or "sent" in p for p in paths), paths
