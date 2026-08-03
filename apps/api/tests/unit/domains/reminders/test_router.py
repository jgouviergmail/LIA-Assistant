"""Cancelling one reminder, exactly.

The briefing card offered no action: a reminder opened the chat, and cancelling
meant asking in prose. The agent path exists (`cancel_reminder_tool` + a HITL
draft) but resolves the target through the model, from a content substring —
two reminders worded alike and the wrong one goes.

This route takes the reminder's own id. The confirmation moves to the card
(an AlertDialog, like deleting a routine) rather than disappearing: a deletion
still asks before it acts, it simply asks where the reader is.

Ownership is enforced in the WHERE clause, and a foreign or unknown id is
answered identically — a 404 that cannot be used to probe whether someone
else's reminder exists.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.exceptions import ResourceNotFoundError
from src.domains.reminders.models import ReminderStatus
from src.domains.reminders.router import cancel_reminder
from src.domains.reminders.service import ReminderService

pytestmark = pytest.mark.unit


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4())


class TestCancel:
    async def test_cancels_the_reminder_named_by_its_id(self) -> None:
        user = _user()
        reminder_id = uuid.uuid4()
        db = AsyncMock()

        with patch("src.domains.reminders.router.ReminderService") as service_cls:
            service_cls.return_value.cancel_reminder = AsyncMock(return_value=MagicMock())

            await cancel_reminder(reminder_id=reminder_id, user=user, db=db)

            service_cls.return_value.cancel_reminder.assert_awaited_once_with(
                reminder_id=reminder_id, user_id=user.id
            )
        db.commit.assert_awaited_once()

    async def test_an_unknown_reminder_is_a_404_and_commits_nothing(self) -> None:
        user = _user()
        db = AsyncMock()

        with patch("src.domains.reminders.router.ReminderService") as service_cls:
            service_cls.return_value.cancel_reminder = AsyncMock(
                side_effect=ResourceNotFoundError("reminder", "nope")
            )

            with pytest.raises(ResourceNotFoundError):
                await cancel_reminder(reminder_id=uuid.uuid4(), user=user, db=db)

        db.commit.assert_not_awaited()

    async def test_another_users_reminder_is_indistinguishable_from_a_missing_one(self) -> None:
        """The router hands the owner down; the service is what refuses.

        Both cases surface the same 404: a different status would tell an
        attacker whether the id exists on another account. This test covers the
        ROUTER's half — that it never calls the service without an owner. The
        refusal itself is enforced one layer down and pinned by
        `TestOwnershipIsEnforcedByTheService` below, against the real service.
        """
        user = _user()

        with patch("src.domains.reminders.router.ReminderService") as service_cls:
            service_cls.return_value.cancel_reminder = AsyncMock(
                side_effect=ResourceNotFoundError("reminder", "nope")
            )

            with pytest.raises(ResourceNotFoundError):
                await cancel_reminder(reminder_id=uuid.uuid4(), user=user, db=AsyncMock())

            # The owner travels with every call: a router that dropped it
            # would turn the id into a global key.
            kwargs = service_cls.return_value.cancel_reminder.await_args.kwargs
            assert kwargs["user_id"] == user.id


class TestOwnershipIsEnforcedByTheService:
    """The layer that actually decides, exercised without mocking it away.

    The router test above mocks `ReminderService`, so on its own it proves the
    owner is PASSED, never that anything refuses. `get_by_id` reads the row
    and compares its owner in Python — an implementation detail the caller must
    not depend on, but one whose OUTCOME is a security property: an id
    belonging to someone else must be answered exactly like an absent one, and
    must never reach a mutation.
    """

    @staticmethod
    def _service(found: object) -> ReminderService:
        service = ReminderService(AsyncMock())
        service.repository = MagicMock()
        service.repository.get_by_id = AsyncMock(return_value=found)
        service.repository.cancel_reminder = AsyncMock()
        return service

    async def test_a_foreign_reminder_raises_the_same_error_as_a_missing_one(self) -> None:
        mine = uuid.uuid4()
        theirs = SimpleNamespace(
            id=uuid.uuid4(), user_id=uuid.uuid4(), status=ReminderStatus.PENDING.value
        )

        foreign = self._service(theirs)
        with pytest.raises(ResourceNotFoundError) as refused:
            await foreign.cancel_reminder(reminder_id=theirs.id, user_id=mine)

        absent = self._service(None)
        with pytest.raises(ResourceNotFoundError) as missing:
            await absent.cancel_reminder(reminder_id=theirs.id, user_id=mine)

        # Same type AND same wording: a message that differed would answer the
        # question the status code refuses to.
        assert type(refused.value) is type(missing.value)
        assert str(refused.value) == str(missing.value)

    async def test_a_foreign_reminder_is_never_cancelled(self) -> None:
        """The refusal must precede the write, not merely report on it."""
        theirs = SimpleNamespace(
            id=uuid.uuid4(), user_id=uuid.uuid4(), status=ReminderStatus.PENDING.value
        )
        service = self._service(theirs)

        with pytest.raises(ResourceNotFoundError):
            await service.cancel_reminder(reminder_id=theirs.id, user_id=uuid.uuid4())

        service.repository.cancel_reminder.assert_not_awaited()

    async def test_the_owner_cancels_their_own(self) -> None:
        """The guard must not be so tight that it refuses everyone."""
        mine = uuid.uuid4()
        own = SimpleNamespace(id=uuid.uuid4(), user_id=mine, status=ReminderStatus.PENDING.value)
        service = self._service(own)

        await service.cancel_reminder(reminder_id=own.id, user_id=mine)

        service.repository.cancel_reminder.assert_awaited_once_with(own)
