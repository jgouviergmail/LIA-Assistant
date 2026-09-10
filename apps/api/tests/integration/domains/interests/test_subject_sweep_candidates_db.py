"""The two subject sweeps against real PostgreSQL: what a cap actually keeps.

A capped read with no ``ORDER BY`` returns whatever the plan yields, and a
table that is not moving yields the SAME rows every time. Measured 2026-09-10,
both sweeps read ``.distinct().limit(50)`` unordered, so the nightly job whose
docstring promised "every user with active interests" served an arbitrary
fifty — the same fifty, for the life of the instance.

Only a real database can settle this: a stubbed session returns the list the
stub was handed, in the order the stub chose, which is precisely the fact
under test.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.interests.models import InterestStatus, UserInterest
from src.domains.users.models import User
from src.infrastructure.scheduler.interest_subject_clustering import (
    refresh_candidates_statement,
    stale_candidates_statement,
)

pytestmark = pytest.mark.integration

#: Enough candidates that a cap must leave some out — the only case where the
#: ordering is observable at all.
POPULATION = 6
CAP = 3
BASE = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def population(async_session: AsyncSession) -> list[uuid.UUID]:
    """Six users, each with one unlabelled active interest, staggered in time.

    Returns:
        Their ids, OLDEST interest first — the order the backlog must serve.
    """
    ids: list[uuid.UUID] = []
    for rank in range(POPULATION):
        user = User(
            email=f"sweep-{uuid.uuid4().hex[:10]}@example.com",
            hashed_password="x",
            full_name=f"Sweep {rank}",
            is_active=True,
        )
        async_session.add(user)
        await async_session.flush()
        interest = UserInterest(
            user_id=user.id,
            topic=f"topic-{rank}",
            status=InterestStatus.ACTIVE.value,
            subject=None,
            last_mentioned_at=BASE,
        )
        async_session.add(interest)
        await async_session.flush()
        # `updated_at` carries `onupdate`, so it is written explicitly rather
        # than assumed: the ordering under test reads this column and nothing
        # else may be trusted to have set it to a known value.
        interest.updated_at = BASE + timedelta(minutes=rank)
        ids.append(user.id)
    await async_session.commit()
    return ids


async def _ids(session: AsyncSession, statement: object) -> list[uuid.UUID]:
    rows = await session.execute(statement)  # type: ignore[arg-type]
    return [row[0] for row in rows.all()]


class TestTheBacklogIsServedOldestFirst:
    """It drains, so it is deterministic — and the cap keeps the oldest end."""

    async def test_the_cap_keeps_the_longest_waiting_users(
        self, async_session: AsyncSession, population: list[uuid.UUID]
    ) -> None:
        served = await _ids(async_session, stale_candidates_statement(limit=CAP))
        assert served == population[:CAP]

    async def test_the_order_is_stable_across_reads(
        self, async_session: AsyncSession, population: list[uuid.UUID]
    ) -> None:
        first = await _ids(async_session, stale_candidates_statement(limit=CAP))
        second = await _ids(async_session, stale_candidates_statement(limit=CAP))
        assert first == second

    async def test_a_labelled_user_leaves_the_backlog(
        self, async_session: AsyncSession, population: list[uuid.UUID]
    ) -> None:
        """What makes the backlog drain: the oldest one served is gone next run."""
        oldest = population[0]
        interest = (
            await async_session.execute(
                UserInterest.__table__.select().where(UserInterest.user_id == oldest)
            )
        ).first()
        assert interest is not None
        await async_session.execute(
            UserInterest.__table__.update()
            .where(UserInterest.user_id == oldest)
            .values(subject="labelled")
        )
        await async_session.commit()
        served = await _ids(async_session, stale_candidates_statement(limit=CAP))
        assert oldest not in served
        assert served == population[1 : CAP + 1]


class TestTheRefreshStarvesNobody:
    """It never drains, so a stable order would pin the same users forever."""

    async def test_the_sample_reaches_beyond_one_batch(
        self, async_session: AsyncSession, population: list[uuid.UUID]
    ) -> None:
        """The defect, stated as a property: the cap is a budget, not a wall.

        Twenty draws of three from six. A stable order returns one fixed
        triple every time — the measured behaviour. The probability that a
        fair sample leaves any given user out of all twenty draws is
        2**-20, so a red here is a real regression, not a flake.
        """
        seen: set[uuid.UUID] = set()
        for _ in range(20):
            seen.update(await _ids(async_session, refresh_candidates_statement(limit=CAP)))
        assert seen == set(population)

    async def test_every_draw_respects_the_cap(
        self, async_session: AsyncSession, population: list[uuid.UUID]
    ) -> None:
        for _ in range(5):
            assert len(await _ids(async_session, refresh_candidates_statement(limit=CAP))) == CAP
