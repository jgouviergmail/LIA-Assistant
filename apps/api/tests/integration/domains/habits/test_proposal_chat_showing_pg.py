"""Which habit proposal a chat answer shows, claimed on a real PostgreSQL (ADR-375).

The chat shows at most one proposal under an answer: the one of the turn's own
domain when it is open, else one the chat never showed, at most one per gap,
each one again only after the repeat delay. What a unit double cannot prove:
the choice and the stamp happen under the person's lock, a busy person is
SKIPPED rather than awaited (an answer never waits for a card), two turns
at once show one proposal, and the door the chat calls hands the card the
proposal's facts — or, on a row it cannot read, spends no showing.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.domains.habits import chat_proposal
from src.domains.habits.models import HabitProposal, ProposalKind, ProposalStatus
from src.domains.habits.proposal_repository import HabitProposalRepository
from src.domains.users.models import User

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
GAP = timedelta(hours=24)
REPEAT = timedelta(days=7)
AUTOMATE = "automate_need"


async def _user(db: AsyncSession) -> uuid.UUID:
    user = User(
        email=f"chat-showing-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x" * 60,
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    await db.flush()
    return user.id


async def _open(
    db: AsyncSession, user_id: uuid.UUID, key: str, *, created: datetime, kind: str = AUTOMATE
) -> uuid.UUID:
    repo = HabitProposalRepository(db)
    assert await repo.open(user_id, kind, key, {"domain": key})
    (row,) = [r for r in await repo.list_for_user(user_id) if (r.kind, r.key) == (kind, key)]
    # The creation instant orders « the oldest never shown »: pinned, not the clock's.
    await db.execute(
        update(HabitProposal).where(HabitProposal.id == row.id).values(created_at=created)
    )
    return row.id


async def _claim(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    now: datetime = NOW,
    preferred: tuple[tuple[str, str], ...] = (),
) -> HabitProposal | None:
    return await HabitProposalRepository(db).claim_chat_showing(
        user_id, preferred=preferred, now=now, gap=GAP, repeat=REPEAT
    )


class TestWhichProposal:
    async def test_the_proposal_of_the_turns_domain_comes_first(
        self, db_session: AsyncSession
    ) -> None:
        user_id = await _user(db_session)
        await _open(db_session, user_id, "weather", created=NOW - timedelta(days=9))
        email = await _open(db_session, user_id, "email", created=NOW - timedelta(days=2))

        shown = await _claim(db_session, user_id, preferred=((AUTOMATE, "email"),))

        assert shown is not None and shown.id == email
        assert shown.chat_shown_at == NOW

    async def test_without_a_match_the_oldest_never_shown_one_comes(
        self, db_session: AsyncSession
    ) -> None:
        user_id = await _user(db_session)
        await _open(db_session, user_id, "event", created=NOW - timedelta(days=5))
        oldest = await _open(db_session, user_id, "weather", created=NOW - timedelta(days=9))
        await _open(db_session, user_id, "email", created=NOW - timedelta(days=1))

        shown = await _claim(db_session, user_id, preferred=((AUTOMATE, "task"),))

        assert shown is not None and shown.id == oldest

    async def test_only_the_owners_open_proposals_are_shown(self, db_session: AsyncSession) -> None:
        user_id, stranger = await _user(db_session), await _user(db_session)
        await _open(db_session, stranger, "weather", created=NOW - timedelta(days=9))
        refused = await _open(db_session, user_id, "email", created=NOW - timedelta(days=9))
        dismissed = await _open(db_session, user_id, "event", created=NOW - timedelta(days=8))
        repo = HabitProposalRepository(db_session)
        await repo.decide(refused, user_id, ProposalStatus.REFUSED, None, now=NOW)
        await repo.decide(dismissed, user_id, ProposalStatus.DISMISSED, None, now=NOW)

        assert await _claim(db_session, user_id, preferred=((AUTOMATE, "email"),)) is None

    async def test_nothing_open_shows_nothing(self, db_session: AsyncSession) -> None:
        assert await _claim(db_session, await _user(db_session)) is None


class TestHowOften:
    async def test_one_showing_per_gap_whatever_became_of_it(
        self, db_session: AsyncSession
    ) -> None:
        user_id = await _user(db_session)
        first = await _open(db_session, user_id, "weather", created=NOW - timedelta(days=9))
        second = await _open(db_session, user_id, "email", created=NOW - timedelta(days=8))

        assert (shown := await _claim(db_session, user_id)) is not None and shown.id == first
        # Accepted since: the day's showing still counts.
        await HabitProposalRepository(db_session).decide(
            first, user_id, ProposalStatus.ACCEPTED, None, now=NOW
        )
        within = await _claim(
            db_session,
            user_id,
            now=NOW + GAP - timedelta(minutes=1),
            preferred=((AUTOMATE, "email"),),
        )
        after = await _claim(db_session, user_id, now=NOW + GAP)

        assert within is None
        assert after is not None and after.id == second

    async def test_a_shown_proposal_returns_only_for_its_domain_after_the_repeat(
        self, db_session: AsyncSession
    ) -> None:
        user_id = await _user(db_session)
        email = await _open(db_session, user_id, "email", created=NOW - timedelta(days=9))
        mine = ((AUTOMATE, "email"),)
        assert (await _claim(db_session, user_id, preferred=mine)) is not None

        too_soon = await _claim(
            db_session, user_id, now=NOW + REPEAT - timedelta(hours=1), preferred=mine
        )
        not_asked = await _claim(db_session, user_id, now=NOW + REPEAT)
        asked = await _claim(db_session, user_id, now=NOW + REPEAT, preferred=mine)

        assert (too_soon, not_asked) == (None, None)
        assert asked is not None and asked.id == email
        assert asked.chat_shown_at == NOW + REPEAT


@pytest_asyncio.fixture
async def committed(async_engine: Any, test_database_url: str) -> Any:
    """Sessions whose writes really commit (several connections), plus the clean-up."""
    engine = create_async_engine(test_database_url, echo=False)
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    marker = f"chat_showing_{uuid.uuid4().hex}@test.local"
    yield sessions, marker
    async with sessions() as session:
        await session.execute(delete(User).where(User.email == marker))
        await session.commit()
    await engine.dispose()


async def _committed_person(sessions: Any, marker: str, keys: tuple[str, ...]) -> uuid.UUID:
    async with sessions() as session:
        user = User(email=marker, hashed_password="x", is_active=True, is_verified=True)
        session.add(user)
        await session.flush()
        for days, key in enumerate(keys):
            await _open(session, user.id, key, created=NOW - timedelta(days=10 - days))
        await session.commit()
        return user.id


async def test_a_busy_person_is_skipped_never_awaited(committed: Any) -> None:
    """A decision in flight holds the person: the answer goes out without a card."""
    sessions, marker = committed
    user_id = await _committed_person(sessions, marker, ("weather",))
    async with sessions() as deciding:
        await HabitProposalRepository(deciding).lock_owner(user_id)
        async with sessions() as turn:
            started = time.monotonic()
            shown = await asyncio.wait_for(_claim(turn, user_id), timeout=5)
            elapsed = time.monotonic() - started
            await turn.commit()
        await deciding.commit()

    assert shown is None
    assert elapsed < 1.0


async def test_two_turns_at_once_show_one_proposal(committed: Any) -> None:
    """Two tabs answering at the same instant: one card, never two in the gap."""
    sessions, marker = committed
    user_id = await _committed_person(sessions, marker, ("weather", "email"))

    async def turn() -> uuid.UUID | None:
        async with sessions() as session:
            shown = await _claim(session, user_id)
            await asyncio.sleep(0.05)  # hold the person while the other turn arrives
            await session.commit()
            return shown.id if shown is not None else None

    results = await asyncio.gather(turn(), turn())

    assert sum(shown is not None for shown in results) == 1


AUTOMATE_FACTS = {
    "domain": "weather",
    "cadence": "weekdays",
    "weekday": None,
    "hour": 7,
    "minute": 30,
    "distinct_days": 14,
    "active_days": 22,
    "part_of_day": "morning",
    "existing_routine": None,
}
SETTINGS = SimpleNamespace(
    recurrence_suggestion_enabled=True,
    habits_proposal_chat_gap_hours=24,
    habits_proposal_chat_repeat_days=7,
)


@pytest.fixture
def chat_door(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> AsyncSession:
    """The chat's door on the test database: each session it opens is a savepoint
    (a failure rolls back what it did, as the production context does), and the
    person's switch is read from that same database."""

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        async with db_session.begin_nested():
            yield db_session

    async def capability() -> bool:
        return True

    monkeypatch.setattr(chat_proposal, "get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.get_db_context", session)
    monkeypatch.setattr(chat_proposal, "habits_capability_enabled", capability)
    return db_session


class TestTheChatsDoor:
    async def test_the_claimed_proposal_reaches_the_card_as_its_facts(
        self, chat_door: AsyncSession
    ) -> None:
        user_id = await _user(chat_door)
        repo = HabitProposalRepository(chat_door)
        assert await repo.open(user_id, AUTOMATE, "weather", AUTOMATE_FACTS)

        shown = await chat_proposal.claim_chat_proposal(
            user_id, "weather", settings=SETTINGS, now=NOW
        )

        assert shown is not None
        assert (shown.kind, shown.key, shown.facts.model_dump()) == (
            ProposalKind.AUTOMATE_NEED,
            "weather",
            AUTOMATE_FACTS,
        )
        stamped = await chat_door.scalar(
            select(HabitProposal.chat_shown_at).where(HabitProposal.id == shown.id)
        )
        assert stamped == NOW

    async def test_learning_switched_off_shows_nothing_and_stamps_nothing(
        self, chat_door: AsyncSession
    ) -> None:
        user_id = await _user(chat_door)
        await chat_door.execute(update(User).where(User.id == user_id).values(habits_enabled=False))
        assert await HabitProposalRepository(chat_door).open(
            user_id, AUTOMATE, "weather", AUTOMATE_FACTS
        )

        shown = await chat_proposal.claim_chat_proposal(
            user_id, "weather", settings=SETTINGS, now=NOW
        )

        assert shown is None
        stamps = await chat_door.scalars(
            select(HabitProposal.chat_shown_at).where(HabitProposal.user_id == user_id)
        )
        assert list(stamps) == [None]

    async def test_a_row_the_card_cannot_read_spends_no_showing(
        self, chat_door: AsyncSession
    ) -> None:
        user_id = await _user(chat_door)
        assert await HabitProposalRepository(chat_door).open(
            user_id, AUTOMATE, "weather", {"domain": "weather"}
        )

        with pytest.raises(ValidationError):
            await chat_proposal.claim_chat_proposal(user_id, None, settings=SETTINGS, now=NOW)

        stamps = await chat_door.scalars(
            select(HabitProposal.chat_shown_at).where(HabitProposal.user_id == user_id)
        )
        assert list(stamps) == [None]
