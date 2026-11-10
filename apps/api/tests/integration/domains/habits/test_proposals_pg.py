"""Habit proposals on a real PostgreSQL (ADR-375).

What a unit double cannot prove: one row per (person, kind, key), the status
CHECK, a decision that only an OPEN row can take (two clicks, two connections,
one winner), the reopen that waits for its date, a refusal that stays, and a
page whose total comes from the same filtered statement.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import delete, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.domains.habits.models import HabitProposal, ProposalStatus
from src.domains.habits.proposal_repository import HabitProposalRepository
from src.domains.users.models import User

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 8, 6, 0, tzinfo=UTC)


async def _user(db: AsyncSession) -> uuid.UUID:
    user = User(
        email=f"proposals-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x" * 60,
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    await db.flush()
    return user.id


async def _open(
    repo: HabitProposalRepository, user_id: uuid.UUID, key: str = "event"
) -> HabitProposal:
    await repo.open(user_id, "automate_need", key, {"domain": key, "distinct_days": 12})
    (row,) = [r for r in await repo.list_for_user(user_id) if r.key == key]
    return row


class TestLifecycle:
    async def test_open_refresh_withdraw_cycle(self, db_session: AsyncSession) -> None:
        repo = HabitProposalRepository(db_session)
        user_id = await _user(db_session)
        row = await _open(repo, user_id)
        assert row.status == ProposalStatus.OPEN.value

        assert await repo.refresh_open(row.id, {"domain": "event", "distinct_days": 14}) is True
        await db_session.refresh(row)
        assert row.payload["distinct_days"] == 14

        assert await repo.withdraw_open(row.id) is True
        assert await repo.list_for_user(user_id) == []

    async def test_opening_twice_keeps_one_row(self, db_session: AsyncSession) -> None:
        repo = HabitProposalRepository(db_session)
        user_id = await _user(db_session)
        await repo.open(user_id, "automate_need", "event", {"n": 1})
        await repo.open(user_id, "automate_need", "event", {"n": 2})
        rows = await repo.list_for_user(user_id)
        assert len(rows) == 1 and rows[0].payload == {"n": 1}

    async def test_dismissed_reopens_after_resurface(self, db_session: AsyncSession) -> None:
        repo = HabitProposalRepository(db_session)
        user_id = await _user(db_session)
        row = await _open(repo, user_id)
        decided = await repo.decide(
            row.id,
            user_id,
            ProposalStatus.DISMISSED,
            resurface_after=NOW + timedelta(days=14),
            now=NOW,
        )
        assert decided is not None and decided.status == ProposalStatus.DISMISSED.value

        assert await repo.reopen(row.id, {"domain": "event"}, now=NOW + timedelta(days=13)) is False
        assert await repo.reopen(row.id, {"domain": "event"}, now=NOW + timedelta(days=14)) is True
        await db_session.refresh(row)
        assert (row.status, row.resurface_after, row.decided_at, row.chat_shown_at) == (
            ProposalStatus.OPEN.value,
            None,
            None,
            None,
        )

    async def test_refused_is_a_tombstone(self, db_session: AsyncSession) -> None:
        repo = HabitProposalRepository(db_session)
        user_id = await _user(db_session)
        row = await _open(repo, user_id)
        await repo.decide(row.id, user_id, ProposalStatus.REFUSED, resurface_after=None, now=NOW)

        assert await repo.reopen(row.id, {}, now=NOW + timedelta(days=3650)) is False
        assert await repo.withdraw_open(row.id) is False
        assert await repo.refusal_counts(user_id) == {"automate_need": 1}

    async def test_a_decision_needs_an_open_row_of_its_owner(
        self, db_session: AsyncSession
    ) -> None:
        repo = HabitProposalRepository(db_session)
        owner = await _user(db_session)
        stranger = await _user(db_session)
        row = await _open(repo, owner)
        assert await repo.decide(row.id, stranger, ProposalStatus.ACCEPTED, None, now=NOW) is None
        assert await repo.decide(row.id, owner, ProposalStatus.ACCEPTED, None, now=NOW) is not None
        assert await repo.decide(row.id, owner, ProposalStatus.REFUSED, None, now=NOW) is None


class TestReads:
    async def test_list_open_page_and_exact_total(self, db_session: AsyncSession) -> None:
        repo = HabitProposalRepository(db_session)
        user_id = await _user(db_session)
        for key in ("event", "email", "task"):
            await repo.open(user_id, "automate_need", key, {"domain": key})
        decided = (await repo.list_for_user(user_id))[0]
        await repo.decide(decided.id, user_id, ProposalStatus.DISMISSED, None, now=NOW)

        page, total = await repo.page_open(user_id, limit=1, offset=0)
        assert total == 2 and len(page) == 1
        rest, total_again = await repo.page_open(user_id, limit=5, offset=1)
        assert total_again == 2 and len(rest) == 1 and rest[0].id != page[0].id
        assert await repo.count_open(user_id) == 2

    async def test_an_empty_page_still_states_the_total(self, db_session: AsyncSession) -> None:
        repo = HabitProposalRepository(db_session)
        user_id = await _user(db_session)
        await repo.open(user_id, "automate_need", "event", {})
        page, total = await repo.page_open(user_id, limit=5, offset=10)
        assert (page, total) == ([], 1)


class TestConstraints:
    async def test_an_undeclared_status_is_refused_by_the_database(
        self, db_session: AsyncSession
    ) -> None:
        user_id = await _user(db_session)
        with pytest.raises(DBAPIError):
            await db_session.execute(
                text(
                    "INSERT INTO habit_proposals (id, user_id, kind, key, payload, status, "
                    "created_at, updated_at) VALUES (:id, :u, 'automate_need', 'event', '{}', "
                    "'exploded', now(), now())"
                ),
                {"id": uuid.uuid4(), "u": user_id},
            )
        await db_session.rollback()

    async def test_an_undeclared_kind_is_refused_by_the_database(
        self, db_session: AsyncSession
    ) -> None:
        user_id = await _user(db_session)
        with pytest.raises(DBAPIError):
            await db_session.execute(
                text(
                    "INSERT INTO habit_proposals (id, user_id, kind, key, payload, status, "
                    "created_at, updated_at) VALUES (:id, :u, 'shortcut', 'event', '{}', "
                    "'open', now(), now())"
                ),
                {"id": uuid.uuid4(), "u": user_id},
            )
        await db_session.rollback()


@pytest_asyncio.fixture
async def committed(async_engine: Any, test_database_url: str) -> Any:
    """Sessions whose writes really commit (two connections), plus the clean-up."""
    engine = create_async_engine(test_database_url, echo=False)
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    marker = f"proposals_{uuid.uuid4().hex}@test.local"
    yield sessions, marker
    async with sessions() as session:
        await session.execute(delete(User).where(User.email == marker))
        await session.commit()
    await engine.dispose()


async def test_accept_is_claimed_once(committed: Any) -> None:
    """Review focus 2: two clicks on two connections, exactly one decision lands."""
    sessions, marker = committed
    async with sessions() as session:
        user = User(email=marker, hashed_password="x", is_active=True, is_verified=True)
        session.add(user)
        await session.flush()
        repo = HabitProposalRepository(session)
        row = await _open(repo, user.id)
        await session.commit()
        user_id, proposal_id = user.id, row.id

    async def click() -> bool:
        async with sessions() as session:
            won = await HabitProposalRepository(session).decide(
                proposal_id, user_id, ProposalStatus.ACCEPTED, None, now=NOW
            )
            await asyncio.sleep(0.05)  # hold the row while the other click waits
            await session.commit()
            return won is not None

    results = await asyncio.gather(click(), click())
    assert sorted(results) == [False, True]


async def test_forget_everything_removes_the_proposals(db_session: AsyncSession) -> None:
    """« Tout oublier » removes what LIA learned AND what it proposed from it."""
    from src.domains.habits.forgetting import forget_habit_data

    repo = HabitProposalRepository(db_session)
    user_id, other = await _user(db_session), await _user(db_session)
    await repo.open(user_id, "automate_need", "event", {})
    row = await _open(repo, user_id, key="email")
    await repo.decide(row.id, user_id, ProposalStatus.REFUSED, None, now=NOW)
    await repo.open(other, "automate_need", "event", {})

    await forget_habit_data(db_session, user_id)

    assert await repo.list_for_user(user_id) == []
    assert len(await repo.list_for_user(other)) == 1
