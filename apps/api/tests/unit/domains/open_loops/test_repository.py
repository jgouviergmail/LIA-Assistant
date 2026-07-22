"""Unit tests for OpenLoopRepository (P5, Lot 2).

Atomic-transition semantics (conditional UPDATE claims) are asserted on the
rowcount contract with a mocked session; real-database concurrency is covered
by the integration suite.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domains.open_loops.repository import OpenLoopRepository


def _db_with_result(**attrs) -> tuple[MagicMock, MagicMock]:
    result = MagicMock(**attrs)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.flush = AsyncMock()
    return db, result


@pytest.mark.unit
class TestCloseLoop:
    """close_loop claims OPEN→CLOSED atomically (conditional UPDATE)."""

    async def test_close_returns_true_when_claimed(self):
        db, result = _db_with_result(rowcount=1)
        repo = OpenLoopRepository(db)

        closed = await repo.close_loop(uuid4(), uuid4(), reason="conversational")

        assert closed is True
        db.execute.assert_awaited_once()

    async def test_close_returns_false_when_already_closed(self):
        db, _ = _db_with_result(rowcount=0)
        repo = OpenLoopRepository(db)

        closed = await repo.close_loop(uuid4(), uuid4(), reason="api")

        assert closed is False


@pytest.mark.unit
class TestExpireStale:
    """expire_stale flips OPEN loops older than the cutoff, returns count."""

    async def test_returns_expired_rowcount(self):
        from datetime import UTC, datetime

        db, _ = _db_with_result(rowcount=3)
        repo = OpenLoopRepository(db)

        count = await repo.expire_stale(uuid4(), cutoff=datetime.now(UTC))

        assert count == 3


@pytest.mark.unit
class TestBumpNudged:
    """bump_nudged updates cooldown fields for the surfaced loops."""

    async def test_noop_on_empty_ids(self):
        db, _ = _db_with_result(rowcount=0)
        repo = OpenLoopRepository(db)

        await repo.bump_nudged([], user_id=uuid4())

        db.execute.assert_not_awaited()

    async def test_updates_when_ids_present(self):
        db, _ = _db_with_result(rowcount=2)
        repo = OpenLoopRepository(db)

        await repo.bump_nudged([uuid4(), uuid4()], user_id=uuid4())

        db.execute.assert_awaited_once()

    async def test_ownership_enforced_in_where_clause(self):
        """Defense-in-depth (same doctrine as close_loop): the UPDATE must be
        scoped to the owner — foreign loop ids silently no-op."""
        db, _ = _db_with_result(rowcount=1)
        repo = OpenLoopRepository(db)

        await repo.bump_nudged([uuid4()], user_id=uuid4())

        stmt = db.execute.await_args.args[0]
        compiled = str(stmt)
        assert "open_loops.user_id =" in compiled


@pytest.mark.unit
class TestListOpenForUser:
    """list_open_for_user returns OPEN loops, oldest deadline first."""

    async def test_returns_scalars(self):
        loop = MagicMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [loop]
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)
        repo = OpenLoopRepository(db)

        loops = await repo.list_open_for_user(uuid4(), limit=10)

        assert loops == [loop]
