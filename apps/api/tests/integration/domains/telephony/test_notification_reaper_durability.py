"""The return-notification reaper retries what reached nobody, up to its cap (audit AC-003).

The reaper used to file « delivered » on any dispatch that did not raise, and a
dispatch never raises: an SSE event alone — an open tab or nobody — retired the
row for good. These tests run the REAL reaper against real PostgreSQL, its own
sessions included: the row's outbox transitions are conditional UPDATEs on a
``native_enum=False`` column, which only a real server can prove.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.domains.telephony.models import NotificationStatus, PhoneCall, PhoneCallStatus
from src.domains.telephony.reapers import telephony_notification_reaper
from src.domains.users.models import User
from tests.helpers.notifications import (
    ScriptedChannels,
    ScriptedDispatcher,
    scripted_dispatcher,
    sse_only,
)

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def pending_return(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> AsyncIterator[UUID]:
    """A committed owner and one PENDING return past the reaper's grace window."""
    owner = uuid4()
    call = uuid4()
    async with AsyncSession(async_engine) as db:
        db.add(
            User(
                id=owner,
                email=f"reaper-{owner}@example.test",
                full_name="Fictional caller",
                is_active=True,
                is_verified=True,
                is_superuser=False,
                timezone="UTC",
            )
        )
        await db.flush()
        committed_user_ids.append(owner)
        db.add(
            PhoneCall(
                id=call,
                user_id=owner,
                callee_display="Marie",
                callee_phone="encrypted-number",
                objective="ask availability",
                status=PhoneCallStatus.COMPLETED,
                completed_at=datetime.now(UTC)
                - timedelta(seconds=settings.telephony_notification_grace_seconds + 60),
                notification_status=NotificationStatus.PENDING,
                notification_payload={"content": "She is free Tuesday.", "title": "Call back"},
            )
        )
        await db.commit()
    yield call


async def _outbox(engine: AsyncEngine, call_id: UUID) -> tuple[NotificationStatus | None, int]:
    async with AsyncSession(engine) as db:
        call = await db.get(PhoneCall, call_id)
        assert call is not None
        return call.notification_status, call.notification_attempts


async def test_a_return_only_a_live_event_carried_is_retried_until_the_cap(
    async_engine: AsyncEngine, pending_return: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    channels = sse_only()
    monkeypatch.setattr(
        "src.infrastructure.proactive.notification.NotificationDispatcher",
        scripted_dispatcher(channels),
    )
    cap = settings.telephony_notification_max_attempts

    for attempt in range(1, cap):
        await telephony_notification_reaper()
        assert await _outbox(async_engine, pending_return) == (NotificationStatus.PENDING, attempt)

    await telephony_notification_reaper()
    assert await _outbox(async_engine, pending_return) == (NotificationStatus.FAILED, cap)

    # A retired row is never fetched again: no further dispatch, nothing moves.
    await telephony_notification_reaper()
    assert len(channels.sent) == cap
    assert await _outbox(async_engine, pending_return) == (NotificationStatus.FAILED, cap)


async def test_a_return_that_reached_the_person_is_delivered_once(
    async_engine: AsyncEngine, pending_return: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    channels = ScriptedChannels(archived=False, fcm_success=1)
    monkeypatch.setattr(
        "src.infrastructure.proactive.notification.NotificationDispatcher",
        scripted_dispatcher(channels),
    )

    await telephony_notification_reaper()
    await telephony_notification_reaper()

    assert await _outbox(async_engine, pending_return) == (NotificationStatus.DELIVERED, 0)
    assert len(channels.sent) == 1


class _ArchiveFailsInSQL(ScriptedDispatcher):
    """The archive's statement fails ON THE CALLER'S SESSION, as a real database error does."""

    async def _archive_message(
        self, user: User, content: str, metadata: Mapping[str, object], db: AsyncSession
    ) -> dict[str, object]:
        await db.execute(text("SELECT 1 / 0"))
        raise AssertionError("unreachable: the statement above raises")


async def test_an_archive_that_failed_in_sql_still_counts_the_attempt(
    async_engine: AsyncEngine, pending_return: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A database error aborts the transaction the caller's failure path writes on.

    Left aborted, that path raises in its turn: the attempt is never counted, the
    row never reaches its cap, and the rest of the batch dies behind it.
    """
    channels = sse_only()
    monkeypatch.setattr(
        "src.infrastructure.proactive.notification.NotificationDispatcher",
        lambda **flags: _ArchiveFailsInSQL(channels, **flags),
    )

    await telephony_notification_reaper()

    assert await _outbox(async_engine, pending_return) == (NotificationStatus.PENDING, 1)
