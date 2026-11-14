"""A source sync keeps its lease for as long as its documents embed.

A sync renewed its lease before each thread or file it READ, then embedded what
it had queued without renewing anything. Measured in production on 2026-11-09:
a label of 2,502 threads embedded for 13 minutes under a 5-minute lease, the
reaper re-drove a second full sync beside the first one (221 threads done
twice) and the document reaper requeued 32 of its documents — all of it in the
minutes the provider's quota was already exhausted.

These tests pin the keeper itself: its cadence is the published setting, it
never outlives the work it serves, a renewal that fails costs the work nothing,
and a native worker is left to the renewal it already owns.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.rag_spaces import source_lease_keepalive as keepalive
from src.domains.rag_spaces.jobs_repository import DRIVE_SOURCE_TABLE, MAIL_SOURCE_TABLE
from src.domains.rag_spaces.source_lease_keepalive import source_lease_kept

pytestmark = pytest.mark.unit

#: The cadence under test, in seconds: short enough for a fast test, long
#: enough for the event loop to interleave the work and the renewal.
_CADENCE = 0.01
#: How long a test waits for something that must happen within a few cadences.
_PATIENCE = 2.0


class _Renewals:
    """The repository's heartbeat, answering from a script and counting."""

    def __init__(self, answers: list[Any] | None = None) -> None:
        self._answers = list(answers or [])
        self.calls: list[tuple[uuid.UUID, int, str]] = []
        #: One entry per session the renewal opened.
        self.sessions: list[object] = []
        self.reached = asyncio.Event()
        self.wanted = 1

    async def heartbeat_source(self, source_id: uuid.UUID, ttl: int, *, table: str) -> bool:
        self.calls.append((source_id, ttl, table))
        answer = self._answers.pop(0) if self._answers else True
        if len(self.calls) >= self.wanted:
            self.reached.set()
        if isinstance(answer, Exception):
            raise answer
        return bool(answer)

    async def wait_for(self, count: int) -> None:
        self.wanted = count
        if len(self.calls) >= count:
            return
        self.reached.clear()
        await asyncio.wait_for(self.reached.wait(), _PATIENCE)


@pytest.fixture
def renewals(monkeypatch: pytest.MonkeyPatch) -> _Renewals:
    spy = _Renewals()

    @asynccontextmanager
    async def _session() -> AsyncIterator[object]:
        db = object()
        spy.sessions.append(db)
        yield db

    monkeypatch.setattr(keepalive, "get_db_context", _session)
    monkeypatch.setattr(keepalive, "RAGJobsRepository", lambda _db: spy)
    monkeypatch.setattr(keepalive.settings, "rag_job_heartbeat_interval_seconds", _CADENCE)
    return spy


def _renewal_tasks() -> list[asyncio.Task[Any]]:
    return [t for t in asyncio.all_tasks() if t.get_name() == keepalive.RENEWAL_TASK_NAME]


async def test_the_lease_is_renewed_on_the_published_cadence_while_the_work_runs(
    renewals: _Renewals,
) -> None:
    source_id = uuid.uuid4()

    async with source_lease_kept(source_id, table=MAIL_SOURCE_TABLE):
        await renewals.wait_for(3)

    ttl = keepalive.settings.rag_job_lease_ttl_seconds
    assert renewals.calls[:3] == [(source_id, ttl, MAIL_SOURCE_TABLE)] * 3
    # One short session per renewal: nothing is held across the wait between two.
    assert len(renewals.sessions) >= 3
    assert len({id(db) for db in renewals.sessions}) == len(renewals.sessions)


async def test_the_table_renewed_is_the_one_the_caller_names(renewals: _Renewals) -> None:
    async with source_lease_kept(uuid.uuid4(), table=DRIVE_SOURCE_TABLE):
        await renewals.wait_for(1)

    assert renewals.calls[0][2] == DRIVE_SOURCE_TABLE


async def test_no_renewal_outlives_the_work(renewals: _Renewals) -> None:
    async with source_lease_kept(uuid.uuid4(), table=MAIL_SOURCE_TABLE):
        await renewals.wait_for(1)
        assert len(_renewal_tasks()) == 1

    seen = len(renewals.calls)
    await asyncio.sleep(_CADENCE * 10)

    assert _renewal_tasks() == []
    assert len(renewals.calls) == seen


async def test_work_that_fails_keeps_its_own_error_and_stops_the_renewal(
    renewals: _Renewals,
) -> None:
    with pytest.raises(RuntimeError, match="embedding broke"):
        async with source_lease_kept(uuid.uuid4(), table=MAIL_SOURCE_TABLE):
            await renewals.wait_for(1)
            raise RuntimeError("embedding broke")

    assert _renewal_tasks() == []


async def test_a_renewal_that_fails_costs_the_work_nothing_and_the_next_one_runs(
    renewals: _Renewals,
) -> None:
    """The lease outlives several cadences: one missed renewal is not a lost lease."""
    renewals._answers = [ConnectionError("database restarting"), True, True]

    async with source_lease_kept(uuid.uuid4(), table=MAIL_SOURCE_TABLE):
        await renewals.wait_for(3)
        finished = "the work went on"

    assert finished == "the work went on"
    assert len(renewals.calls) >= 3


async def test_a_refused_renewal_stops_renewing_and_leaves_the_work_alone(
    renewals: _Renewals,
) -> None:
    """Refused means the source is no longer SYNCING — unlinked, or settled by
    someone else. There is nothing left to keep; its documents went with it."""
    renewals._answers = [True, False]

    async with source_lease_kept(uuid.uuid4(), table=MAIL_SOURCE_TABLE):
        await renewals.wait_for(2)
        await asyncio.sleep(_CADENCE * 10)
        still_running = "the work went on"

    assert still_running == "the work went on"
    assert len(renewals.calls) == 2


async def test_a_native_worker_is_left_to_the_renewal_it_already_owns(
    renewals: _Renewals, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A native source worker renews around each external call, under its own
    unique claim (source_worker_runtime): a second, anonymous renewal beside it
    would be refused by the repository and would only add noise."""
    monkeypatch.setattr(keepalive, "current_source_worker", lambda: MagicMock())

    async with source_lease_kept(uuid.uuid4(), table=MAIL_SOURCE_TABLE):
        await asyncio.sleep(_CADENCE * 10)

    assert renewals.calls == []
    assert _renewal_tasks() == []


async def test_cancelling_the_work_stops_the_renewal_and_stays_a_cancellation(
    renewals: _Renewals,
) -> None:
    entered = asyncio.Event()

    async def work() -> None:
        async with source_lease_kept(uuid.uuid4(), table=MAIL_SOURCE_TABLE):
            entered.set()
            await asyncio.sleep(_PATIENCE * 10)

    task = asyncio.create_task(work())
    await asyncio.wait_for(entered.wait(), _PATIENCE)
    await renewals.wait_for(1)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert _renewal_tasks() == []


async def test_a_renewal_cancelled_in_the_middle_of_its_write_is_joined_before_the_work_returns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The renewal owns a database session: leaving it to close beside its
    caller is how two writers end up on one row."""
    in_write = asyncio.Event()
    closed: list[str] = []

    @asynccontextmanager
    async def _session() -> AsyncIterator[object]:
        try:
            yield object()
        finally:
            await asyncio.sleep(0)
            closed.append("session closed")

    repo = MagicMock()

    async def _slow_heartbeat(*_args: Any, **_kwargs: Any) -> bool:
        in_write.set()
        await asyncio.sleep(_PATIENCE * 10)
        return True

    repo.heartbeat_source = AsyncMock(side_effect=_slow_heartbeat)
    monkeypatch.setattr(keepalive, "get_db_context", _session)
    monkeypatch.setattr(keepalive, "RAGJobsRepository", lambda _db: repo)
    monkeypatch.setattr(keepalive.settings, "rag_job_heartbeat_interval_seconds", _CADENCE)

    async with source_lease_kept(uuid.uuid4(), table=MAIL_SOURCE_TABLE):
        await asyncio.wait_for(in_write.wait(), _PATIENCE)

    assert closed == ["session closed"]
    assert _renewal_tasks() == []
