"""Writing the consultation register once, at the end of the turn (ADR-263, lot 4).

The recorder is the only place the treatments reach the database, and it sits
in a ``finally``: a turn that raises, and a turn that is cancelled, both close
their books. That is the same invariant ADR-248 states for the ReAct loop —
*a turn that stops mid-flight closes its own books* — applied to the register
rather than to the message history.

The shield is not decoration. Measured on this loop:

    ONE cancellation (a client disconnects)      naive: writes   shielded: writes
    cancellation RE-DELIVERED during cleanup     naive: NOTHING  shielded: writes
    (container stop, an enclosing timeout)

A Raspberry Pi restarting is the ordinary case, not the exotic one.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.agents.effects.treatment_recorder import treatment_recorder
from src.domains.agents.effects.treatments import Treatment

pytestmark = [pytest.mark.unit]


def _row(tool_name: str = "get_emails_tool") -> Treatment:
    return Treatment(
        user_id="11111111-1111-4111-8111-111111111111",
        thread_id="thread-1",
        run_id="run-1",
        source="user",
        execution_mode="pipeline",
        tool_name=tool_name,
        mutation_policy="read",
        outcome="ok",
        duration_ms=12,
        occurred_at=datetime.now(UTC),
    )


class _Recorded:
    """A stand-in for the repository, capturing what the turn wrote."""

    def __init__(self, *, fails: bool = False, slow: float = 0.0) -> None:
        self.batches: list[list[Treatment]] = []
        self._fails = fails
        self._slow = slow

    def __call__(self, _db: Any) -> Any:
        return self

    async def record_batch(self, rows: list[Treatment]) -> int:
        if self._slow:
            await asyncio.sleep(self._slow)
        if self._fails:
            raise RuntimeError("the register is unwritable")
        self.batches.append(list(rows))
        return len(rows)


@asynccontextmanager
async def _session() -> Any:
    yield AsyncMock()


@pytest.fixture
def recorded() -> Any:
    repository = _Recorded()
    with (
        patch("src.domains.agents.effects.treatment_recorder.TreatmentRepository", repository),
        patch("src.infrastructure.database.session.get_db_context", _session),
    ):
        yield repository


class TestOneBatchPerTurn:
    async def test_a_normal_turn_writes_its_rows_once(self, recorded: Any) -> None:
        async with treatment_recorder(run_id="run-1") as rows:
            rows.append(_row())
            rows.append(_row("get_calendar_events_tool"))

        assert len(recorded.batches) == 1, "the register must be written in ONE batch"
        assert len(recorded.batches[0]) == 2

    async def test_an_empty_turn_writes_nothing(self, recorded: Any) -> None:
        async with treatment_recorder(run_id="run-1"):
            pass

        assert recorded.batches == [], "an empty turn opened a session for nothing"

    async def test_the_collector_is_published_inside(self, recorded: Any) -> None:
        from src.domains.agents.effects.treatments import collected_treatments, observe

        async with treatment_recorder(run_id="run-1"):
            observe(_row())
            assert len(collected_treatments()) == 1

        assert len(recorded.batches[0]) == 1

    async def test_the_collector_is_gone_outside(self, recorded: Any) -> None:
        from src.domains.agents.effects.treatments import collected_treatments

        async with treatment_recorder(run_id="run-1"):
            pass

        assert list(collected_treatments()) == []


class TestATurnThatStopsClosesItsBooks:
    async def test_a_raising_turn_still_writes(self, recorded: Any) -> None:
        with pytest.raises(RuntimeError, match="the turn failed"):
            async with treatment_recorder(run_id="run-1") as rows:
                rows.append(_row())
                raise RuntimeError("the turn failed")

        assert len(recorded.batches) == 1, "a failed turn lost its register"

    async def test_a_cancelled_turn_still_writes(self, recorded: Any) -> None:
        async def _turn() -> None:
            async with treatment_recorder(run_id="run-1") as rows:
                rows.append(_row())
                await asyncio.sleep(60)

        task = asyncio.create_task(_turn())
        await asyncio.sleep(0.02)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert len(recorded.batches) == 1, "a cancelled turn lost its register"

    async def test_a_RE_DELIVERED_cancellation_still_writes(self) -> None:
        """A container stopping cancels again while cleanup runs."""
        repository = _Recorded(slow=0.05)

        async def _turn() -> None:
            async with treatment_recorder(run_id="run-1") as rows:
                rows.append(_row())
                await asyncio.sleep(60)

        with (
            patch("src.domains.agents.effects.treatment_recorder.TreatmentRepository", repository),
            patch("src.infrastructure.database.session.get_db_context", _session),
        ):
            task = asyncio.create_task(_turn())
            await asyncio.sleep(0.02)
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()  # the second cancel, delivered during the flush
            with pytest.raises(asyncio.CancelledError):
                await task

        assert len(repository.batches) == 1, "a re-delivered cancellation lost the register"

    async def test_the_cancellation_is_still_honoured(self, recorded: Any) -> None:
        """Writing the register must not turn a cancelled turn into a live one."""

        async def _turn() -> None:
            async with treatment_recorder(run_id="run-1") as rows:
                rows.append(_row())
                await asyncio.sleep(60)

        task = asyncio.create_task(_turn())
        await asyncio.sleep(0.02)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert task.cancelled()


class TestWritingNeverBreaksTheTurn:
    async def test_an_unwritable_register_does_not_fail_the_turn(self) -> None:
        repository = _Recorded(fails=True)
        with (
            patch("src.domains.agents.effects.treatment_recorder.TreatmentRepository", repository),
            patch("src.infrastructure.database.session.get_db_context", _session),
        ):
            async with treatment_recorder(run_id="run-1") as rows:
                rows.append(_row())

        assert repository.batches == []

    async def test_an_unwritable_register_does_not_mask_the_turns_error(self) -> None:
        """The turn's own exception is what the caller must see."""
        repository = _Recorded(fails=True)
        with (
            patch("src.domains.agents.effects.treatment_recorder.TreatmentRepository", repository),
            patch("src.infrastructure.database.session.get_db_context", _session),
        ):
            with pytest.raises(RuntimeError, match="the turn failed"):
                async with treatment_recorder(run_id="run-1") as rows:
                    rows.append(_row())
                    raise RuntimeError("the turn failed")
