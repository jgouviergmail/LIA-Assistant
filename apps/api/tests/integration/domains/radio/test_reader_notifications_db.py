"""Integration: the radio's notifications read against a real PostgreSQL (ADR-324).

What only a server proves: the newest end of the day is kept, a hidden run row
never reaches the station, the ``proactive_`` prefix is matched literally (its
``_`` is a LIKE wildcard), and another conversation's rows stay where they are.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.peers.constants import PROACTIVE_PEER_IMAGE_TYPE, PROACTIVE_PEER_MESSAGE_TYPE
from src.domains.radio.readers import notifications as module
from src.domains.users.models import User

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 26, 7, 0, tzinfo=UTC)


async def _user(session: AsyncSession, email: str) -> User:
    user = User(email=email, hashed_password="x", is_active=True, is_superuser=False)
    session.add(user)
    await session.commit()
    session.add(
        Conversation(id=user.id, user_id=user.id, title="t", message_count=0, total_tokens=0)
    )
    await session.commit()
    return user


def _message(
    conversation_id: object, minutes_ago: int, kind: str, **extra: object
) -> ConversationMessage:
    return ConversationMessage(
        conversation_id=conversation_id,
        role="assistant",
        content=f"**Update** {minutes_ago} minutes ago",
        message_metadata={"type": kind},
        created_at=NOW - timedelta(minutes=minutes_ago),
        **extra,
    )


async def test_the_newest_visible_notifications_of_the_listener_only(
    async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    listener = await _user(async_session, "radio_notif_listener@test.local")
    stranger = await _user(async_session, "radio_notif_stranger@test.local")
    async_session.add_all(
        [
            _message(listener.id, 300, "proactive_interest"),
            _message(listener.id, 200, "proactive_birthday"),
            _message(listener.id, 100, "proactive_heartbeat"),
            _message(listener.id, 60, "proactive_interest"),
            _message(listener.id, 30, "proactive_interest", hidden=True),  # a run's row
            _message(listener.id, 20, "proactiveXinterest"),  # `_` is not a wildcard here
            _message(listener.id, 10, "live_turn"),
            _message(listener.id, 60 * 30, "proactive_interest"),  # yesterday morning
            _message(stranger.id, 5, "proactive_interest"),
        ]
    )
    await async_session.commit()

    @contextlib.asynccontextmanager
    async def _ctx() -> AsyncIterator[AsyncSession]:
        yield async_session

    monkeypatch.setattr(module, "get_db_context", _ctx)
    drafts = await module.read_notifications(listener.id, now=NOW, tz=UTC)

    assert [draft.text.split('"')[1] for draft in drafts] == [
        "Update 60 minutes ago",
        "Update 100 minutes ago",
        "Update 200 minutes ago",
    ]
    assert "(heartbeat)" in drafts[1].text


async def test_a_flash_reads_what_came_after_its_watermark_oldest_first(
    async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-324 decision 32: what LIA wrote since the station last looked, never again."""
    listener = await _user(async_session, "radio_flash_listener@test.local")
    stranger = await _user(async_session, "radio_flash_stranger@test.local")
    async_session.add_all(
        [
            _message(listener.id, 50, "proactive_interest"),  # before the watermark
            _message(listener.id, 40, "proactive_heartbeat"),  # the watermark itself
            _message(listener.id, 30, "proactive_interest"),
            _message(listener.id, 20, "proactive_interest", hidden=True),  # a run's row
            _message(listener.id, 15, "live_turn"),
            _message(listener.id, 10, "proactive_birthday"),
            _message(listener.id, 8, "proactive_interest"),
            _message(listener.id, 5, "proactive_heartbeat"),
            _message(stranger.id, 2, "proactive_interest"),
        ]
    )
    await async_session.commit()

    @contextlib.asynccontextmanager
    async def _ctx() -> AsyncIterator[AsyncSession]:
        yield async_session

    monkeypatch.setattr(module, "get_db_context", _ctx)
    notes = await module.read_flash_notes(listener.id, after=NOW - timedelta(minutes=40), limit=3)

    assert [note.excerpt for note in notes] == [
        "Update 30 minutes ago",
        "Update 10 minutes ago",
        "Update 8 minutes ago",
    ]
    assert [note.topic for note in notes] == ["interest", "birthday", "interest"]
    assert notes[0].sent_at == NOW - timedelta(minutes=30)
    assert all(isinstance(note.id, str) for note in notes)


async def test_a_connections_words_relayed_by_lia_are_never_the_stations(
    async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A message or an image a connection sent through LIA is THEIRS: neither a flash
    nor the corner tells it as LIA's notification (owner decision 2026-09-27). Left
    out by the query itself, so three of them never use up a flash's bound."""
    listener = await _user(async_session, "radio_relay_listener@test.local")
    async_session.add_all(
        [
            _message(listener.id, 50, PROACTIVE_PEER_MESSAGE_TYPE),
            _message(listener.id, 45, PROACTIVE_PEER_MESSAGE_TYPE),
            _message(listener.id, 40, PROACTIVE_PEER_IMAGE_TYPE),
            _message(listener.id, 30, "proactive_peer_connection"),  # LIA's own words
            _message(listener.id, 10, "proactive_interest"),
        ]
    )
    await async_session.commit()

    @contextlib.asynccontextmanager
    async def _ctx() -> AsyncIterator[AsyncSession]:
        yield async_session

    monkeypatch.setattr(module, "get_db_context", _ctx)
    notes = await module.read_flash_notes(listener.id, after=NOW - timedelta(minutes=60), limit=3)
    drafts = await module.read_notifications(listener.id, now=NOW, tz=UTC)

    assert [note.topic for note in notes] == ["peer connection", "interest"]
    assert ["(peer connection)" in d.text or "(interest)" in d.text for d in drafts] == [
        True,
        True,
    ]
