"""The relationship timeline against real PostgreSQL (owner request 2026-10-24).

What only the database proves: each source's keyset resumes exactly where the
merged order left off — ties on one instant across sources AND within one —
so walking the pages serves every record once, newest first.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.memories.models import Memory, MemoryCategory
from src.domains.open_loops.models import OpenLoop, OpenLoopStatus
from src.domains.relations import timeline
from src.domains.telephony.models import PhoneCall, PhoneCallStatus
from src.domains.users.models import User

pytestmark = pytest.mark.integration

NAME = "Ana Example"
AT = datetime(2026, 10, 20, 9, 30, tzinfo=UTC)


@pytest.fixture
async def owner(async_session: AsyncSession) -> User:
    user = User(
        email="timeline_owner@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        full_name="Timeline Owner",
    )
    async_session.add(user)
    await async_session.flush()
    return user


def _loop(user_id: UUID, at: datetime, subject: str) -> OpenLoop:
    return OpenLoop(
        user_id=user_id,
        counterparty=NAME,
        subject=subject,
        direction="user_owes",
        status=OpenLoopStatus.OPEN.value,
        created_at=at,
    )


def _call(user_id: UUID, at: datetime, objective: str, callee: str = NAME) -> PhoneCall:
    return PhoneCall(
        user_id=user_id,
        callee_display=callee,
        callee_phone="encrypted-by-the-service",
        objective=objective,
        status=PhoneCallStatus.COMPLETED,
        created_at=at,
    )


def _memory(user_id: UUID, at: datetime, content: str) -> Memory:
    return Memory(
        user_id=user_id,
        content=content,
        category=MemoryCategory.RELATIONSHIP.value,
        emotional_weight=0,
        trigger_topic="",
        usage_nuance="",
        importance=0.5,
        char_count=len(content),
        created_at=at,
    )


async def test_the_pages_serve_every_record_once_newest_first(
    async_session: AsyncSession, owner: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    earlier = AT - timedelta(days=2)
    async_session.add_all(
        [
            # Three kinds on ONE instant, and two loops on another.
            _loop(owner.id, AT, "lend the drill"),
            _call(owner.id, AT, "birthday"),
            _memory(owner.id, AT, f"{NAME} loves hiking"),
            _loop(owner.id, earlier, "return the book"),
            _loop(owner.id, earlier, "send the photos"),
            _call(owner.id, AT - timedelta(days=5), "dinner"),
            _memory(owner.id, AT - timedelta(days=9), f"{NAME} moved to Lyon"),
            # Someone else's records never join hers.
            _call(owner.id, AT, "plumber", callee="Somebody Else"),
        ]
    )
    await async_session.flush()

    @asynccontextmanager
    async def same_session() -> AsyncIterator[AsyncSession]:
        yield async_session

    monkeypatch.setattr(timeline, "get_db_context", same_session)
    monkeypatch.setattr(settings, "relations_max_items_per_section", 2)
    monkeypatch.setattr(settings, "peers_enabled", False)

    first = await timeline.build_timeline(owner.id, NAME, cursor=None, include_sms=False)
    served = list(first.items)
    cursor = first.next_cursor
    pages = 1
    while cursor is not None:
        page = await timeline.build_timeline(owner.id, NAME, cursor=cursor, include_sms=False)
        assert len(page.items) <= 2
        served.extend(page.items)
        cursor = page.next_cursor
        pages += 1
        assert pages < 10, "the walk must end"

    keys = [(item.at, item.kind, timeline._item_id(item)) for item in served]
    # Every one of the seven records of hers, once: none skipped at a page
    # boundary, none served twice.
    assert len(keys) == len(set(keys)) == 7
    assert keys == sorted(keys, reverse=True)
    # At one instant the declared kind order breaks the tie.
    assert [item.kind for item in served[:3]] == ["open_loop", "memory", "call"]
    subjects = [item.open_loop.subject for item in served if item.open_loop]
    assert set(subjects) == {"lend the drill", "return the book", "send the photos"}
    assert all(item.call.objective != "plumber" for item in served if item.call)
