"""Integration: the journal's « done » reads against a real PostgreSQL (ADR-324 decision 41).

What only a server proves: the reminders that rang today are the visible rows the
scheduler stamped, of the listener's own conversation, since THEIR local midnight; the
tickets closed today are the board's closed statuses on its visibility predicate, since
that midnight, oldest closing first — a stranger's row never reaches the station.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import REMINDER_NOTIFICATION_MESSAGE_TYPE
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.radio.readers import reminders as reminders_module
from src.domains.radio.readers import tickets as tickets_module
from src.domains.users.models import User
from src.domains.workboard.constants import AssigneeKind, TicketPriority, TicketStatus
from src.domains.workboard.models import WorkboardTicket

pytestmark = pytest.mark.integration

#: 13:00 UTC on 2026-09-26 — 15:00 two hours east.
NOW = datetime(2026, 9, 26, 13, 0, tzinfo=UTC)
PLUS_TWO = timezone(timedelta(hours=2))


async def _user(session: AsyncSession, email: str, *, conversation: bool = True) -> User:
    user = User(email=email, hashed_password="x", is_active=True, is_superuser=False)
    session.add(user)
    await session.commit()
    if conversation:
        session.add(
            Conversation(id=user.id, user_id=user.id, title="t", message_count=0, total_tokens=0)
        )
        await session.commit()
    return user


def _ring(conversation_id: object, minutes_ago: int, **extra: object) -> ConversationMessage:
    return ConversationMessage(
        conversation_id=conversation_id,
        role="assistant",
        content=f"🔔 **Reminder** {minutes_ago} minutes ago",
        message_metadata={
            "type": REMINDER_NOTIFICATION_MESSAGE_TYPE,
            "reminder_id": f"r{minutes_ago}",
        },
        created_at=NOW - timedelta(minutes=minutes_ago),
        **extra,
    )


def _ticket(
    owner_id: object, title: str, *, status: str, changed_minutes_ago: int
) -> WorkboardTicket:
    return WorkboardTicket(
        owner_user_id=owner_id,
        title=title,
        status=status,
        priority=TicketPriority.MEDIUM.value,
        assignee_kind=AssigneeKind.HUMAN.value,
        assignee_user_id=None,
        position=0,
        created_by="user",
        status_changed_at=NOW - timedelta(minutes=changed_minutes_ago),
        run_attempts=0,
        run_count=0,
        nudge_count=0,
    )


@pytest.fixture
def one_session(async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    @contextlib.asynccontextmanager
    async def _ctx() -> AsyncIterator[AsyncSession]:
        yield async_session

    monkeypatch.setattr(reminders_module, "get_db_context", _ctx)
    monkeypatch.setattr(tickets_module, "get_db_context", _ctx)


async def test_the_reminders_that_rang_today_of_the_listener_alone_oldest_first(
    async_session: AsyncSession, one_session: None
) -> None:
    listener = await _user(async_session, "radio_rings_listener@test.local")
    stranger = await _user(async_session, "radio_rings_stranger@test.local")
    async_session.add_all(
        [
            _ring(listener.id, 60 * 14),  # 23:00 UTC yesterday — 01:00 TODAY two hours east
            _ring(listener.id, 60 * 16),  # 21:00 UTC yesterday: yesterday everywhere here
            _ring(listener.id, 240),
            _ring(listener.id, 30),
            _ring(listener.id, 20, hidden=True),  # a run's row: never heard
            ConversationMessage(
                conversation_id=listener.id,
                role="assistant",
                content="an interest update",
                message_metadata={"type": "proactive_interest"},
                created_at=NOW - timedelta(minutes=10),
            ),
            _ring(stranger.id, 5),
        ]
    )
    await async_session.commit()

    utc_drafts = await reminders_module.read_reminders_done(listener.id, now=NOW, tz=UTC)
    assert [d.key for d in utc_drafts] == ["done:reminder:r240", "done:reminder:r30"]
    assert utc_drafts[0].text.startswith("Reminder rang on Saturday 2026-09-26, 09:00")

    east_drafts = await reminders_module.read_reminders_done(listener.id, now=NOW, tz=PLUS_TWO)
    assert [d.key for d in east_drafts] == [
        "done:reminder:r840",
        "done:reminder:r240",
        "done:reminder:r30",
    ]


async def test_a_listener_without_a_conversation_has_no_rings(
    async_session: AsyncSession, one_session: None
) -> None:
    silent = await _user(async_session, "radio_rings_silent@test.local", conversation=False)
    assert await reminders_module.read_reminders_done(silent.id, now=NOW, tz=UTC) == []


async def test_the_tickets_closed_today_on_the_listener_s_board_oldest_closing_first(
    async_session: AsyncSession, one_session: None
) -> None:
    owner = await _user(async_session, "radio_closed_owner@test.local", conversation=False)
    stranger = await _user(async_session, "radio_closed_stranger@test.local", conversation=False)
    async_session.add_all(
        [
            _ticket(
                owner.id, "Closed at nine", status=TicketStatus.DONE.value, changed_minutes_ago=240
            ),
            _ticket(
                owner.id, "Closed at noon", status=TicketStatus.DONE.value, changed_minutes_ago=60
            ),
            _ticket(
                owner.id,
                "Closed yesterday",
                status=TicketStatus.DONE.value,
                changed_minutes_ago=60 * 30,
            ),
            _ticket(
                owner.id,
                "Still open, touched today",
                status=TicketStatus.IN_PROGRESS.value,
                changed_minutes_ago=30,
            ),
            _ticket(
                stranger.id,
                "Someone else's",
                status=TicketStatus.DONE.value,
                changed_minutes_ago=30,
            ),
        ]
    )
    await async_session.commit()

    drafts = await tickets_module.read_closed_tickets(owner.id, now=NOW, tz=UTC)
    assert [d.text for d in drafts] == [
        'Ticket "Closed at nine" was closed today at 09:00',
        'Ticket "Closed at noon" was closed today at 12:00',
    ]
    assert all(d.key.startswith("done:ticket:") for d in drafts)
