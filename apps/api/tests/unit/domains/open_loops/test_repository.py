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


@pytest.mark.unit
class TestUpdateLoop:
    """The extractor gets the wording wrong sometimes — the user can fix it.

    Same claim shape as ``close_loop``: a conditional UPDATE scoped to the owner
    AND to the OPEN status, so a closed or foreign loop is never edited and the
    caller learns it from the return value rather than from a silent no-op.
    """

    async def test_returns_true_when_the_row_is_claimed(self):
        db, _ = _db_with_result(rowcount=1)
        repo = OpenLoopRepository(db)

        updated = await repo.update_loop(uuid4(), uuid4(), subject="rappeler le plombier mardi")

        assert updated is True
        db.execute.assert_awaited_once()

    async def test_returns_false_when_nothing_matched(self):
        """Closed, expired, or someone else's: no row, no edit."""
        db, _ = _db_with_result(rowcount=0)
        repo = OpenLoopRepository(db)

        assert await repo.update_loop(uuid4(), uuid4(), subject="x") is False

    async def test_editing_nothing_does_not_touch_the_database(self):
        """An empty patch is a no-op, not an UPDATE that only bumps updated_at."""
        db, _ = _db_with_result(rowcount=1)
        repo = OpenLoopRepository(db)

        assert await repo.update_loop(uuid4(), uuid4()) is False
        db.execute.assert_not_awaited()

    async def test_ownership_and_status_are_in_the_where_clause(self):
        """Never filter in Python: a foreign row must not even be selected."""
        db, _ = _db_with_result(rowcount=1)
        repo = OpenLoopRepository(db)

        await repo.update_loop(uuid4(), uuid4(), subject="x")

        rendered = str(db.execute.await_args.args[0])
        assert "user_id" in rendered
        assert "status" in rendered
