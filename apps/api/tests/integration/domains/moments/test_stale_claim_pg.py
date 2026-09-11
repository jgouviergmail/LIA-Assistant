"""A worker that dies mid-flight must not take the moment with it.

Measured against this very server on 2026-09-11, BEFORE the fix: a moment
claimed and never settled was invisible to every statement of the module.
``expire_stale`` reads ``pending`` rows, ``purge_settled`` reads settled ones,
and ``claim_due`` reads ``pending`` — so a row in ``claimed`` was reachable by
none of them. It was still there, untouched, at +365 days.

Three ordinary events produce one: a process killed mid-deploy between the
claim's commit and the settle's, a pool that refuses a connection at settle
time, a serve raising something the sweep's own per-account handler swallows.
The person is never asked, the row is never freed, and nothing says so.

That is exactly the « stale shutdown with two independent actors » the
durable-claim rule names, and the repository's own docstring claimed the
opposite — that a short-lived row's window closes on its own. A closing window
does nothing for a claimed row.

The end is read from the CLAIM's AGE, never from the window, which is what lets
a moment be tried again while it is still worth something. A row whose window
has also closed is reclaimed here and expired by the very next statement, in
the same housekeeping pass.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.domains.moments.models import MomentKind, MomentState, ProactiveMoment
from src.domains.moments.repository import MomentCandidate, MomentRepository
from src.domains.users.models import User

pytestmark = pytest.mark.integration

# Anchored on the real clock: every predicate under test compares instants the
# caller passes, so a frozen literal would drift the day it names.
NOW = datetime.now(UTC)
LEASE = timedelta(minutes=15)


def _candidate(user_id: UUID, *, ref: str = "evt-stale") -> MomentCandidate:
    return MomentCandidate(
        user_id=user_id,
        kind=MomentKind.EVENT_FOLLOWUP.value,
        source_ref=ref,
        due_at=NOW,
        not_after=NOW + timedelta(hours=3),
        payload={"title": "Budget", "score": 3},
    )


@pytest_asyncio.fixture
async def committed(async_engine: Any, test_database_url: str) -> Any:
    """A sessionmaker whose writes really commit, plus its clean-up."""
    engine = create_async_engine(test_database_url, echo=False)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    marker = f"moment_stale_{uuid4().hex}@test.local"
    yield maker, marker
    async with maker() as session:
        await session.execute(delete(User).where(User.email == marker))
        await session.commit()
    await engine.dispose()


async def _seed(maker: Any, email: str) -> UUID:
    """One account holding one pending moment, really committed."""
    async with maker() as session:
        user = User(email=email, hashed_password="x", is_active=True, is_verified=True)
        session.add(user)
        await session.flush()
        user_id = UUID(str(user.id))
        await MomentRepository(session).insert_candidates([_candidate(user_id)])
        await session.commit()
        return user_id


async def _claim(maker: Any, user_id: UUID, owner: str, *, now: datetime = NOW) -> Any:
    async with maker() as session:
        claimed = await MomentRepository(session).claim_due(user_id=user_id, now=now, owner=owner)
        await session.commit()
        return claimed


async def _reclaim(maker: Any, *, now: datetime) -> int:
    async with maker() as session:
        freed = await MomentRepository(session).reclaim_stale(now=now, older_than=LEASE)
        await session.commit()
        return freed


class TestAnAbandonedClaimComesBack:
    async def test_a_stale_claim_returns_to_pending(self, committed: Any) -> None:
        maker, marker = committed
        user_id = await _seed(maker, marker)
        claimed = await _claim(maker, user_id, "worker-that-dies")
        assert claimed is not None

        assert await _reclaim(maker, now=NOW + timedelta(minutes=30)) == 1

        async with maker() as session:
            row = await session.get(ProactiveMoment, claimed.id)
            assert row is not None
            assert row.state == MomentState.PENDING.value
            # The owner goes with the claim: a zombie quoting it must match
            # nothing, and the next claimant writes its own.
            assert row.claim_owner is None
            assert row.claimed_at is None

    async def test_another_worker_can_then_serve_it(self, committed: Any) -> None:
        maker, marker = committed
        user_id = await _seed(maker, marker)
        await _claim(maker, user_id, "dead")

        later = NOW + timedelta(minutes=30)
        await _reclaim(maker, now=later)
        retaken = await _claim(maker, user_id, "alive", now=later)

        assert retaken is not None
        assert retaken.claim_owner == "alive"

    async def test_the_dead_worker_cannot_settle_what_it_lost(self, committed: Any) -> None:
        """The owner token is what keeps a zombie's late write off the row."""
        maker, marker = committed
        user_id = await _seed(maker, marker)
        await _claim(maker, user_id, "dead")

        later = NOW + timedelta(minutes=30)
        await _reclaim(maker, now=later)
        retaken = await _claim(maker, user_id, "alive", now=later)
        assert retaken is not None

        async with maker() as session:
            settled = await MomentRepository(session).settle(
                UUID(str(retaken.id)), owner="dead", state=MomentState.SERVED, now=later
            )
            await session.commit()

        assert settled is False

    async def test_a_fresh_claim_is_never_stolen(self, committed: Any) -> None:
        """A serve legitimately takes seconds; the lease must outlive it."""
        maker, marker = committed
        user_id = await _seed(maker, marker)
        await _claim(maker, user_id, "busy")

        assert await _reclaim(maker, now=NOW + timedelta(minutes=2)) == 0

    async def test_a_settled_row_is_never_reclaimed(self, committed: Any) -> None:
        maker, marker = committed
        user_id = await _seed(maker, marker)
        claimed = await _claim(maker, user_id, "w")
        assert claimed is not None
        async with maker() as session:
            await MomentRepository(session).settle(
                UUID(str(claimed.id)), owner="w", state=MomentState.SERVED, now=NOW
            )
            await session.commit()

        assert await _reclaim(maker, now=NOW + timedelta(hours=5)) == 0

    async def test_a_pending_row_is_left_alone(self, committed: Any) -> None:
        """Nothing was claimed, so there is nothing to give back."""
        maker, marker = committed
        await _seed(maker, marker)

        assert await _reclaim(maker, now=NOW + timedelta(hours=5)) == 0

    async def test_nothing_is_left_behind_once_the_window_closes(self, committed: Any) -> None:
        """Reclaim then expire, in one pass: the leak closes end to end."""
        maker, marker = committed
        user_id = await _seed(maker, marker)
        await _claim(maker, user_id, "dead")

        long_after = NOW + timedelta(hours=6)
        async with maker() as session:
            repo = MomentRepository(session)
            await repo.reclaim_stale(now=long_after, older_than=LEASE)
            expired = await repo.expire_stale(now=long_after)
            await session.commit()

        assert expired == [MomentKind.EVENT_FOLLOWUP.value]

        async with maker() as session:
            purged = await MomentRepository(session).purge_settled(
                before=long_after + timedelta(days=400)
            )
            await session.commit()

        assert purged == 1
