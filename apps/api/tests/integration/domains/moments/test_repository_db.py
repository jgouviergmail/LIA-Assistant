"""Claiming and settling a moment against a real server.

Five things only PostgreSQL can answer, and each is a defect class a
statement-shape test cannot see:

- **the detector re-reads the same window every five minutes.** Without the
  unique key it would file the same event at every pass, and the person would be
  asked about one meeting twenty times. ``ON CONFLICT DO NOTHING`` is a property
  of the server's index, not of the Python that asks for it.
- **two workers, one moment.** ``FOR UPDATE SKIP LOCKED`` lives in the lock
  manager; the race here needs two INDEPENDENT connections, because a
  savepoint-isolated session would never see the other side's committed rows.
- **a settle that lost its moment.** A worker killed mid-flight comes back and
  writes; its write must match NOTHING rather than overwrite a state the sweep
  has since decided.
- **expiry is a bounded statement.** « How did yesterday evening go » is not a
  moment: a row that missed its window is closed, never served late.
- **the purge deletes settled rows and only those.** A predicate that took the
  pending ones with them would silence the feature without a sound.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.domains.moments.models import (
    MomentKind,
    MomentSkipReason,
    MomentState,
    ProactiveMoment,
)
from src.domains.moments.repository import MomentCandidate, MomentRepository
from src.domains.users.models import User

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)


def _candidate(user_id: UUID, *, ref: str = "evt-1", **overrides: Any) -> MomentCandidate:
    """One detected moment, due now and valid for three hours."""
    fields: dict[str, Any] = {
        "user_id": user_id,
        "kind": MomentKind.EVENT_FOLLOWUP.value,
        "source_ref": ref,
        "due_at": NOW,
        "not_after": NOW + timedelta(hours=3),
        "payload": {"title": "Budget", "score": 3},
    }
    fields.update(overrides)
    return MomentCandidate(**fields)


@pytest_asyncio.fixture
async def committed(async_engine: Any, test_database_url: str) -> Any:
    """A sessionmaker whose writes really commit, plus its clean-up.

    Depends on ``async_engine`` so the schema exists. Rows written here outlive
    the test by construction, so the account is deleted at the end — every row
    under test hangs off it by CASCADE.
    """
    engine = create_async_engine(test_database_url, echo=False)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    marker = f"moment_repo_{uuid4().hex}@test.local"
    yield maker, marker
    async with maker() as session:
        await session.execute(delete(User).where(User.email == marker))
        await session.commit()
    await engine.dispose()


async def _seed_account(maker: Any, email: str) -> UUID:
    """One active account, really committed."""
    async with maker() as session:
        user = User(email=email, hashed_password="x", is_active=True, is_verified=True)
        session.add(user)
        await session.commit()
        return UUID(str(user.id))


async def _state_of(maker: Any, moment_id: UUID) -> tuple[str, str | None, str | None]:
    """Read a row back through a fresh session: (state, claim_owner, skip_reason)."""
    async with maker() as session:
        row = await session.get(ProactiveMoment, moment_id)
        assert row is not None
        return row.state, row.claim_owner, row.skip_reason


class TestFilingWhatWasDetected:
    async def test_a_candidate_is_filed_once(self, committed: Any) -> None:
        maker, marker = committed
        user_id = await _seed_account(maker, marker)

        async with maker() as session:
            inserted = await MomentRepository(session).insert_candidates([_candidate(user_id)])
            await session.commit()

        assert inserted == [MomentKind.EVENT_FOLLOWUP.value]

    async def test_the_same_detection_is_never_filed_twice(self, committed: Any) -> None:
        """The detector re-reads the same calendar window at every pass."""
        maker, marker = committed
        user_id = await _seed_account(maker, marker)

        async with maker() as session:
            await MomentRepository(session).insert_candidates([_candidate(user_id)])
            await session.commit()
        async with maker() as session:
            again = await MomentRepository(session).insert_candidates(
                [_candidate(user_id, due_at=NOW + timedelta(minutes=5))]
            )
            await session.commit()

        assert again == []
        async with maker() as session:
            rows = (
                (
                    await session.execute(
                        select(ProactiveMoment).where(ProactiveMoment.user_id == user_id)
                    )
                )
                .scalars()
                .all()
            )
        assert len(rows) == 1
        # The FIRST detection stands: a conflicting insert changes nothing.
        assert rows[0].due_at == NOW

    async def test_two_different_events_are_two_moments(self, committed: Any) -> None:
        maker, marker = committed
        user_id = await _seed_account(maker, marker)

        async with maker() as session:
            inserted = await MomentRepository(session).insert_candidates(
                [_candidate(user_id, ref="evt-1"), _candidate(user_id, ref="evt-2")]
            )
            await session.commit()

        assert len(inserted) == 2

    async def test_filing_nothing_is_not_an_error(self, committed: Any) -> None:
        maker, marker = committed
        await _seed_account(maker, marker)

        async with maker() as session:
            assert await MomentRepository(session).insert_candidates([]) == []


class TestClaimingWhatIsDue:
    async def test_a_due_moment_is_claimed_with_its_owner_token(self, committed: Any) -> None:
        maker, marker = committed
        user_id = await _seed_account(maker, marker)
        async with maker() as session:
            await MomentRepository(session).insert_candidates([_candidate(user_id)])
            await session.commit()

        async with maker() as session:
            claimed = await MomentRepository(session).claim_due(
                user_id=user_id, now=NOW, owner="worker-a"
            )
            await session.commit()

        assert claimed is not None
        state, owner, _ = await _state_of(maker, UUID(str(claimed.id)))
        assert state == MomentState.CLAIMED.value
        assert owner == "worker-a"

    async def test_a_moment_not_yet_due_is_left_alone(self, committed: Any) -> None:
        maker, marker = committed
        user_id = await _seed_account(maker, marker)
        async with maker() as session:
            await MomentRepository(session).insert_candidates(
                [_candidate(user_id, due_at=NOW + timedelta(hours=1))]
            )
            await session.commit()

        async with maker() as session:
            assert (
                await MomentRepository(session).claim_due(
                    user_id=user_id, now=NOW, owner="worker-a"
                )
                is None
            )

    async def test_a_moment_past_its_window_is_never_served_late(self, committed: Any) -> None:
        """« How did yesterday evening go » is not a moment."""
        maker, marker = committed
        user_id = await _seed_account(maker, marker)
        async with maker() as session:
            await MomentRepository(session).insert_candidates(
                [
                    _candidate(
                        user_id,
                        due_at=NOW - timedelta(hours=5),
                        not_after=NOW - timedelta(hours=1),
                    )
                ]
            )
            await session.commit()

        async with maker() as session:
            assert (
                await MomentRepository(session).claim_due(
                    user_id=user_id, now=NOW, owner="worker-a"
                )
                is None
            )

    async def test_another_account_moment_is_out_of_reach(self, committed: Any) -> None:
        maker, marker = committed
        mine = await _seed_account(maker, marker)
        theirs = await _seed_account(maker, f"other_{marker}")
        async with maker() as session:
            await MomentRepository(session).insert_candidates([_candidate(theirs)])
            await session.commit()

        async with maker() as session:
            assert (
                await MomentRepository(session).claim_due(user_id=mine, now=NOW, owner="worker-a")
                is None
            )

        async with maker() as session:
            await session.execute(delete(User).where(User.id == theirs))
            await session.commit()

    async def test_the_oldest_due_moment_comes_first(self, committed: Any) -> None:
        maker, marker = committed
        user_id = await _seed_account(maker, marker)
        async with maker() as session:
            await MomentRepository(session).insert_candidates(
                [
                    _candidate(user_id, ref="recent", due_at=NOW - timedelta(minutes=5)),
                    _candidate(user_id, ref="older", due_at=NOW - timedelta(minutes=50)),
                ]
            )
            await session.commit()

        async with maker() as session:
            claimed = await MomentRepository(session).claim_due(
                user_id=user_id, now=NOW, owner="worker-a"
            )
            await session.commit()

        assert claimed is not None
        assert claimed.source_ref == "older"

    async def test_two_workers_one_moment(self, committed: Any) -> None:
        """The property lives in the server's lock manager, not in our Python."""
        maker, marker = committed
        user_id = await _seed_account(maker, marker)
        async with maker() as session:
            await MomentRepository(session).insert_candidates([_candidate(user_id)])
            await session.commit()

        async def _worker(owner: str) -> str | None:
            async with maker() as session:
                claimed = await MomentRepository(session).claim_due(
                    user_id=user_id, now=NOW, owner=owner
                )
                await session.commit()
                return None if claimed is None else str(claimed.id)

        first, second = await asyncio.gather(_worker("worker-a"), _worker("worker-b"))

        assert [first, second].count(None) == 1, "exactly one worker must win the moment"


class TestSettling:
    async def test_the_holder_settles_it(self, committed: Any) -> None:
        maker, marker = committed
        user_id = await _seed_account(maker, marker)
        async with maker() as session:
            await MomentRepository(session).insert_candidates([_candidate(user_id)])
            await session.commit()
        async with maker() as session:
            claimed = await MomentRepository(session).claim_due(
                user_id=user_id, now=NOW, owner="worker-a"
            )
            await session.commit()
        assert claimed is not None
        moment_id = UUID(str(claimed.id))

        async with maker() as session:
            settled = await MomentRepository(session).settle(
                moment_id,
                owner="worker-a",
                state=MomentState.SERVED,
                now=NOW + timedelta(seconds=30),
            )
            await session.commit()

        assert settled is True
        state, _, _ = await _state_of(maker, moment_id)
        assert state == MomentState.SERVED.value

    async def test_a_skip_carries_its_reason(self, committed: Any) -> None:
        maker, marker = committed
        user_id = await _seed_account(maker, marker)
        async with maker() as session:
            await MomentRepository(session).insert_candidates([_candidate(user_id)])
            await session.commit()
        async with maker() as session:
            claimed = await MomentRepository(session).claim_due(
                user_id=user_id, now=NOW, owner="worker-a"
            )
            await session.commit()
        assert claimed is not None

        async with maker() as session:
            await MomentRepository(session).settle(
                UUID(str(claimed.id)),
                owner="worker-a",
                state=MomentState.SKIPPED,
                skip_reason=MomentSkipReason.QUOTA,
                now=NOW,
            )
            await session.commit()

        state, _, reason = await _state_of(maker, UUID(str(claimed.id)))
        assert state == MomentState.SKIPPED.value
        assert reason == MomentSkipReason.QUOTA.value

    async def test_a_zombie_settle_writes_nothing(self, committed: Any) -> None:
        """A worker killed mid-flight comes back; the sweep has moved on."""
        maker, marker = committed
        user_id = await _seed_account(maker, marker)
        async with maker() as session:
            await MomentRepository(session).insert_candidates([_candidate(user_id)])
            await session.commit()
        async with maker() as session:
            claimed = await MomentRepository(session).claim_due(
                user_id=user_id, now=NOW, owner="worker-a"
            )
            await session.commit()
        assert claimed is not None
        moment_id = UUID(str(claimed.id))

        async with maker() as session:
            settled = await MomentRepository(session).settle(
                moment_id,
                owner="worker-b",
                state=MomentState.SERVED,
                now=NOW,
            )
            await session.commit()

        assert settled is False
        state, owner, _ = await _state_of(maker, moment_id)
        assert state == MomentState.CLAIMED.value
        assert owner == "worker-a"


class TestClosingWhatMissedItsWindow:
    async def test_a_pending_row_past_its_window_expires(self, committed: Any) -> None:
        maker, marker = committed
        user_id = await _seed_account(maker, marker)
        async with maker() as session:
            await MomentRepository(session).insert_candidates(
                [
                    _candidate(
                        user_id,
                        ref="missed",
                        due_at=NOW - timedelta(hours=6),
                        not_after=NOW - timedelta(hours=3),
                    ),
                    _candidate(user_id, ref="live"),
                ]
            )
            await session.commit()

        async with maker() as session:
            expired = await MomentRepository(session).expire_stale(now=NOW)
            await session.commit()

        assert expired == [MomentKind.EVENT_FOLLOWUP.value]
        async with maker() as session:
            rows = {
                row.source_ref: row.state
                for row in (
                    await session.execute(
                        select(ProactiveMoment).where(ProactiveMoment.user_id == user_id)
                    )
                )
                .scalars()
                .all()
            }
        assert rows == {
            "missed": MomentState.EXPIRED.value,
            "live": MomentState.PENDING.value,
        }

    async def test_a_claimed_row_is_not_expired_under_its_holder(self, committed: Any) -> None:
        """Expiry closes what nobody took; a run in flight settles itself."""
        maker, marker = committed
        user_id = await _seed_account(maker, marker)
        async with maker() as session:
            await MomentRepository(session).insert_candidates([_candidate(user_id)])
            await session.commit()
        async with maker() as session:
            claimed = await MomentRepository(session).claim_due(
                user_id=user_id, now=NOW, owner="worker-a"
            )
            await session.commit()
        assert claimed is not None

        async with maker() as session:
            expired = await MomentRepository(session).expire_stale(now=NOW + timedelta(hours=9))
            await session.commit()

        assert expired == []
        state, _, _ = await _state_of(maker, UUID(str(claimed.id)))
        assert state == MomentState.CLAIMED.value


class TestPurging:
    async def test_settled_rows_go_and_live_ones_stay(self, committed: Any) -> None:
        maker, marker = committed
        user_id = await _seed_account(maker, marker)
        async with maker() as session:
            repo = MomentRepository(session)
            await repo.insert_candidates(
                [_candidate(user_id, ref="old"), _candidate(user_id, ref="live")]
            )
            await session.commit()
        async with maker() as session:
            row = (
                await session.execute(
                    select(ProactiveMoment).where(ProactiveMoment.source_ref == "old")
                )
            ).scalar_one()
            row.state = MomentState.SERVED.value
            row.settled_at = NOW - timedelta(days=40)
            await session.commit()

        async with maker() as session:
            purged = await MomentRepository(session).purge_settled(before=NOW - timedelta(days=30))
            await session.commit()

        assert purged == 1
        async with maker() as session:
            remaining = (
                (
                    await session.execute(
                        select(ProactiveMoment).where(ProactiveMoment.user_id == user_id)
                    )
                )
                .scalars()
                .all()
            )
        assert [row.source_ref for row in remaining] == ["live"]

    async def test_a_recently_settled_row_is_kept(self, committed: Any) -> None:
        maker, marker = committed
        user_id = await _seed_account(maker, marker)
        async with maker() as session:
            await MomentRepository(session).insert_candidates([_candidate(user_id)])
            await session.commit()
        async with maker() as session:
            row = (
                await session.execute(
                    select(ProactiveMoment).where(ProactiveMoment.user_id == user_id)
                )
            ).scalar_one()
            row.state = MomentState.SERVED.value
            row.settled_at = NOW - timedelta(days=2)
            await session.commit()

        async with maker() as session:
            purged = await MomentRepository(session).purge_settled(before=NOW - timedelta(days=30))
            await session.commit()

        assert purged == 0
