"""What happens to a reminder that the scheduler picks up but does not send.

``get_and_lock_pending_reminders`` is a LEASE: it selects the rows whose
``trigger_at`` has passed, flips every one of them to ``PROCESSING`` and
flushes, so a second worker skips them. The next tick only ever selects
``PENDING`` rows.

Every path out of the processing loop must therefore either finish the work,
delete the row, or RELEASE the lease. A path that just ``continue``s leaves the
row in ``PROCESSING`` for good: it is never selected again, never sent, never
cleaned up. The user set a reminder and it silently evaporates — the failure
mode is invisible by construction, since nothing errors and nothing logs a
problem.

These tests drive `process_pending_reminders` over a fully stubbed collaborator
set and assert the outcome for each exit: sent, retried, dropped, or deferred.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.reminders.models import ReminderStatus
from src.infrastructure.scheduler.reminder_notification import (
    MAX_RETRIES,
    process_pending_reminders,
)

pytestmark = pytest.mark.unit


def _reminder(**overrides: Any) -> SimpleNamespace:
    """A locked reminder, exactly as the repository hands it over."""
    base: dict[str, Any] = {
        "id": uuid4(),
        "user_id": uuid4(),
        "content": "acheter du pain",
        "original_message": "rappelle-moi d'acheter du pain",
        "created_at": datetime.now(UTC) - timedelta(hours=2),
        "trigger_at": datetime.now(UTC) - timedelta(minutes=1),
        "user_timezone": "Europe/Paris",
        # The lease the repository just took.
        "status": ReminderStatus.PROCESSING.value,
        "retry_count": 0,
        "notification_error": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _user(**overrides: Any) -> SimpleNamespace:
    base: dict[str, Any] = {
        "id": uuid4(),
        "is_active": True,
        "language": "fr",
        "personality_id": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class _Harness:
    """Every collaborator `process_pending_reminders` imports, stubbed."""

    def __init__(self, reminders: list[SimpleNamespace], user: SimpleNamespace | None) -> None:
        self.repo = MagicMock()
        self.repo.get_and_lock_pending_reminders = AsyncMock(return_value=reminders)
        self.repo.delete = AsyncMock()

        self.db = MagicMock()
        self.db.commit = AsyncMock()

        self.user_service = MagicMock()
        self.user_service.get_user_by_id = AsyncMock(return_value=user)

        self.fcm = MagicMock()
        self.fcm.send_reminder_notification = AsyncMock(
            return_value=SimpleNamespace(success_count=1, failure_count=0)
        )

        self.blocked = False

    def _db_context(self) -> Any:
        context = AsyncMock()
        context.__aenter__ = AsyncMock(return_value=self.db)
        context.__aexit__ = AsyncMock(return_value=None)
        return MagicMock(return_value=context)

    def patches(self) -> list[Any]:
        module = "src.infrastructure.scheduler.reminder_notification"
        return [
            patch("src.infrastructure.database.session.get_db_context", self._db_context()),
            patch("src.domains.reminders.repository.ReminderRepository", return_value=self.repo),
            patch("src.domains.users.service.UserService", return_value=self.user_service),
            patch("src.domains.personalities.service.PersonalityService", MagicMock()),
            patch(
                "src.domains.notifications.service.FCMNotificationService", return_value=self.fcm
            ),
            patch(
                "src.domains.usage_limits.service.UsageLimitService.is_user_blocked_for_llm",
                AsyncMock(side_effect=lambda *a, **k: self.blocked),
            ),
            patch("src.infrastructure.cache.redis.get_redis_cache", AsyncMock(return_value=None)),
            patch(f"{module}.get_relevant_memories", AsyncMock(return_value=[])),
            patch(
                f"{module}.generate_reminder_message",
                AsyncMock(
                    return_value=SimpleNamespace(
                        message="N'oublie pas le pain",
                        tokens_in=0,
                        tokens_out=0,
                        tokens_cache=0,
                        model_name="",
                    )
                ),
            ),
        ]


async def _run(harness: _Harness) -> dict[str, Any]:
    """Execute the scheduler pass under the stubbed collaborators."""
    stack = harness.patches()
    for entered in stack:
        entered.start()
    try:
        return await process_pending_reminders()
    finally:
        for entered in reversed(stack):
            entered.stop()


class TestNothingDue:
    async def test_empty_batch_does_no_work(self) -> None:
        harness = _Harness([], _user())

        stats = await _run(harness)

        assert stats == {"processed": 0, "notified": 0, "failed": 0, "skipped": 0}
        harness.repo.delete.assert_not_awaited()


class TestLeaseIsAlwaysResolved:
    """The invariant: no reminder may stay PROCESSING after the pass."""

    async def test_a_rate_limited_user_keeps_their_reminder_for_the_next_tick(self) -> None:
        """The block is TEMPORARY; the reminder must survive it.

        Left in PROCESSING, this reminder would never be selected again — a
        user who happened to hit their LLM budget at the wrong minute would
        lose the reminder outright, with no error anywhere.
        """
        reminder = _reminder()
        user = _user(id=reminder.user_id)
        harness = _Harness([reminder], user)
        harness.blocked = True

        stats = await _run(harness)

        assert stats["skipped"] == 1
        assert stats["notified"] == 0
        harness.repo.delete.assert_not_awaited()
        assert (
            reminder.status == ReminderStatus.PENDING.value
        ), "the lease was not released — this reminder can never fire again"

    async def test_an_inactive_user_keeps_their_reminder_rather_than_a_dangling_lease(
        self,
    ) -> None:
        """Deactivation is reversible; deletion is the purge's job, not ours."""
        reminder = _reminder()
        user = _user(id=reminder.user_id, is_active=False)
        harness = _Harness([reminder], user)

        stats = await _run(harness)

        assert stats["skipped"] == 1
        harness.repo.delete.assert_not_awaited()
        assert reminder.status == ReminderStatus.PENDING.value

    async def test_an_orphan_reminder_is_deleted_not_left_behind(self) -> None:
        """No user means no recipient: the row is dead weight, drop it."""
        reminder = _reminder()
        harness = _Harness([reminder], None)

        stats = await _run(harness)

        assert stats["skipped"] == 1
        harness.repo.delete.assert_awaited_once_with(reminder)


class TestNominalDelivery:
    async def test_a_sent_reminder_is_deleted(self) -> None:
        """One-shot semantics: delivery is the end of the row's life."""
        reminder = _reminder()
        user = _user(id=reminder.user_id)
        harness = _Harness([reminder], user)

        stats = await _run(harness)

        assert stats == {"processed": 1, "notified": 1, "failed": 0, "skipped": 0}
        harness.repo.delete.assert_awaited_once_with(reminder)
        harness.db.commit.assert_awaited()

    async def test_the_notification_carries_the_localized_title_and_the_bell(self) -> None:
        reminder = _reminder()
        user = _user(id=reminder.user_id, language="zh-CN")
        harness = _Harness([reminder], user)

        await _run(harness)

        kwargs = harness.fcm.send_reminder_notification.await_args.kwargs
        assert kwargs["title"] == "提醒"  # not the English fallback
        assert kwargs["body"].startswith("🔔 ")
        assert kwargs["reminder_id"] == str(reminder.id)


class TestFailureRetryLadder:
    async def test_a_first_failure_is_returned_to_the_queue(self) -> None:
        reminder = _reminder(retry_count=0)
        user = _user(id=reminder.user_id)
        harness = _Harness([reminder], user)
        harness.fcm.send_reminder_notification = AsyncMock(side_effect=RuntimeError("fcm down"))

        stats = await _run(harness)

        assert stats["failed"] == 0
        assert reminder.retry_count == 1
        assert reminder.status == ReminderStatus.PENDING.value
        assert reminder.notification_error == "fcm down"
        harness.repo.delete.assert_not_awaited()

    async def test_the_last_allowed_failure_drops_the_reminder(self) -> None:
        """Past MAX_RETRIES the row is deleted rather than retried forever."""
        reminder = _reminder(retry_count=MAX_RETRIES - 1)
        user = _user(id=reminder.user_id)
        harness = _Harness([reminder], user)
        harness.fcm.send_reminder_notification = AsyncMock(side_effect=RuntimeError("fcm down"))

        stats = await _run(harness)

        assert stats["failed"] == 1
        assert reminder.retry_count == MAX_RETRIES
        harness.repo.delete.assert_awaited_once_with(reminder)


class TestBatchIsolation:
    async def test_one_failing_reminder_does_not_stop_the_others(self) -> None:
        """A batch is not transactional: a bad row must not swallow good ones."""
        failing = _reminder(content="échoue")
        healthy = _reminder(content="passe")
        user = _user(id=failing.user_id)
        harness = _Harness([failing, healthy], user)

        calls: list[Any] = []

        async def send(**kwargs: Any) -> Any:
            calls.append(kwargs)
            if len(calls) == 1:
                raise RuntimeError("fcm down")
            return SimpleNamespace(success_count=1, failure_count=0)

        harness.fcm.send_reminder_notification = AsyncMock(side_effect=send)

        stats = await _run(harness)

        assert stats["processed"] == 2
        assert stats["notified"] == 1
        assert failing.status == ReminderStatus.PENDING.value
        harness.repo.delete.assert_awaited_once_with(healthy)
