"""Step 0b of the executor tick: close what has no future (ADR-281, lot 5).

It sits beside the run-history retention for the same reasons — no new
interval to jitter, no new lock — and BEFORE the empty-batch early return,
which is the common tick: a day with nothing due is exactly when a finished
routine must stop looking active.

Housekeeping never costs the tick. Its own session, so a failed statement
cannot poison the batch that follows, and every failure is swallowed and
counted as zero rather than raised.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infrastructure.scheduler import scheduled_action_executor as executor

pytestmark = pytest.mark.unit

_REPO = "src.domains.scheduled_actions.repository.ScheduledActionRepository"
_SESSION = "src.infrastructure.database.session.get_db_context"


def _db() -> tuple[Any, Any]:
    session = MagicMock()
    session.commit = AsyncMock()

    @asynccontextmanager
    async def _ctx() -> Any:
        yield session

    return _ctx, session


class TestClosingFinishedRoutines:
    async def test_it_closes_and_commits(self) -> None:
        ctx, session = _db()
        repo = MagicMock()
        repo.close_finished = AsyncMock(return_value=3)

        with patch(_SESSION, new=ctx), patch(_REPO, MagicMock(return_value=repo)):
            assert await executor._close_finished_routines() == 3

        session.commit.assert_awaited_once()

    async def test_a_quiet_tick_closes_nothing(self) -> None:
        ctx, _ = _db()
        repo = MagicMock()
        repo.close_finished = AsyncMock(return_value=0)

        with patch(_SESSION, new=ctx), patch(_REPO, MagicMock(return_value=repo)):
            assert await executor._close_finished_routines() == 0

    async def test_a_failure_never_costs_the_tick(self) -> None:
        """The batch that follows must still run."""
        ctx, _ = _db()
        repo = MagicMock()
        repo.close_finished = AsyncMock(side_effect=RuntimeError("database gone"))

        with patch(_SESSION, new=ctx), patch(_REPO, MagicMock(return_value=repo)):
            assert await executor._close_finished_routines() == 0

    async def test_a_session_that_cannot_open_is_swallowed_too(self) -> None:
        @asynccontextmanager
        async def _broken() -> Any:
            raise RuntimeError("no pool")
            yield  # pragma: no cover

        with patch(_SESSION, new=_broken):
            assert await executor._close_finished_routines() == 0

    async def test_it_never_asks_the_repository_for_an_instant(self) -> None:
        """The end is read from the trigger the recurrence engine arms.

        A `now` parameter here would be the first half of a second authority
        on when a routine stops — the very column this lot removed.
        """
        ctx, _ = _db()
        repo = MagicMock()
        repo.close_finished = AsyncMock(return_value=1)

        with patch(_SESSION, new=ctx), patch(_REPO, MagicMock(return_value=repo)):
            await executor._close_finished_routines()

        repo.close_finished.assert_awaited_once_with()
