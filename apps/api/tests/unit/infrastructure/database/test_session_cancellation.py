"""A cancellation that lands while a session closes reaches its task.

Both session helpers close their session in a ``finally``, shielded: cut short,
the close would leave the connection checked out of the pool (client
disconnects during SSE streaming, v1.3.0). Until 2026-10-25 the shield sat in
``suppress(CancelledError)``: a cancellation landing DURING the close was
swallowed, the helper returned normally and the cancelled task carried on.
Measured on dev: a worker reload held for more than 36 minutes, because the
lifetime-metrics loop — cancelled, then awaited by the shutdown — went back to
sleep after its ``cancel()``. The swallow also left the close running behind
the helper, and ``AsyncSession.__aexit__`` then started a SECOND close of the
same session beside it.

What holds, for both helpers (the dependency driven the way FastAPI drives a
``yield`` dependency):

* the task ends cancelled, and never runs the code after its block;
* the close runs to its end before the cancellation propagates;
* a session is closed once, even when re-delivered cancellations exhaust the
  grace and the close is left to finish on its own;
* nobody cancelled: a failure of the close itself still reaches the caller.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress
from dataclasses import dataclass, field

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import DATABASE_SESSION_CLOSE_CANCELLATION_GRACE_ATTEMPTS
from src.infrastructure.database import session as session_module
from src.infrastructure.database.session import get_db_context, get_db_session

pytestmark = pytest.mark.unit

type _SessionOpener = Callable[[], AbstractAsyncContextManager[AsyncSession]]

#: Everything below runs in memory: a second is a generous bound for a task
#: that is meant to have stopped, and keeps a regression from hanging the run.
_STOP_PATIENCE_S = 1.0

_HELPERS = pytest.mark.parametrize(
    "open_session",
    [
        pytest.param(get_db_context, id="get_db_context"),
        # FastAPI enters a ``yield`` dependency through ``asynccontextmanager``.
        pytest.param(asynccontextmanager(get_db_session), id="get_db_session"),
    ],
)


@dataclass
class _CloseGate:
    """Holds every close of the test's sessions until the test releases it."""

    started: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)
    finished: asyncio.Event = field(default_factory=asyncio.Event)
    calls: int = 0
    failure: OperationalError | None = None


class _GatedSession(AsyncSession):
    """A real session (no bind: it never connects) whose close the test holds."""

    def __init__(self, gate: _CloseGate) -> None:
        super().__init__()
        self._gate = gate

    async def close(self) -> None:
        self._gate.calls += 1
        self._gate.started.set()
        await self._gate.release.wait()
        if self._gate.failure is not None:
            raise self._gate.failure
        await super().close()
        self._gate.finished.set()


@pytest.fixture
def gate(monkeypatch: pytest.MonkeyPatch) -> _CloseGate:
    held = _CloseGate()
    monkeypatch.setattr(session_module, "AsyncSessionLocal", lambda: _GatedSession(held))
    return held


async def _deliver() -> None:
    """Let the loop hand a pending cancellation to the task that awaits."""
    for _ in range(3):
        await asyncio.sleep(0)


def _closed_when_it_ended(task: asyncio.Task[None], gate: _CloseGate) -> list[bool]:
    """Whether the close had finished at the instant the task ended."""
    seen: list[bool] = []
    task.add_done_callback(lambda _done: seen.append(gate.finished.is_set()))
    return seen


@_HELPERS
async def test_a_cancellation_landing_during_the_close_reaches_its_task(
    open_session: _SessionOpener, gate: _CloseGate
) -> None:
    resumed: list[str] = []

    async def work() -> None:
        async with open_session():
            pass
        resumed.append("the code after the block ran")

    task = asyncio.create_task(work())
    closed = _closed_when_it_ended(task, gate)
    await gate.started.wait()

    task.cancel()
    await _deliver()
    gate.release.set()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert resumed == [], "a cancelled task carried on past its session"
    assert closed == [True], "the connection goes back to the pool before the task ends"


@_HELPERS
async def test_a_cancellation_during_the_work_closes_before_it_propagates(
    open_session: _SessionOpener, gate: _CloseGate
) -> None:
    gate.release.set()
    working = asyncio.Event()

    async def work() -> None:
        async with open_session():
            working.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(work())
    closed = _closed_when_it_ended(task, gate)
    await working.wait()

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed == [True]


@_HELPERS
async def test_re_delivered_cancellations_never_start_a_second_close(
    open_session: _SessionOpener, gate: _CloseGate
) -> None:
    async def work() -> None:
        async with open_session():
            pass

    task = asyncio.create_task(work())
    await gate.started.wait()

    for _ in range(DATABASE_SESSION_CLOSE_CANCELLATION_GRACE_ATTEMPTS):
        task.cancel()
        await _deliver()

    with pytest.raises(asyncio.CancelledError):
        await task
    # Past the grace the close is left to finish on its own — it still does.
    gate.release.set()
    await asyncio.wait_for(gate.finished.wait(), timeout=_STOP_PATIENCE_S)
    assert gate.calls == 1, "a second close ran beside the first one"


@_HELPERS
async def test_a_failed_close_still_reaches_a_task_nobody_cancelled(
    open_session: _SessionOpener, gate: _CloseGate
) -> None:
    gate.failure = OperationalError("ROLLBACK", {}, Exception("connection lost"))
    gate.release.set()

    with pytest.raises(OperationalError):
        async with open_session():
            pass


async def test_a_periodic_loop_cancelled_during_its_close_stops(gate: _CloseGate) -> None:
    """The measured incident: the shutdown cancels a periodic loop, then awaits it."""

    async def periodic() -> None:
        while True:
            try:
                async with get_db_context():
                    pass
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                break

    loop_task = asyncio.create_task(periodic())
    await gate.started.wait()

    loop_task.cancel()
    await _deliver()
    gate.release.set()

    done, _pending = await asyncio.wait({loop_task}, timeout=_STOP_PATIENCE_S)
    try:
        assert loop_task in done, "the shutdown would wait on this loop for ever"
    finally:
        loop_task.cancel()
        with suppress(asyncio.CancelledError):
            await loop_task
