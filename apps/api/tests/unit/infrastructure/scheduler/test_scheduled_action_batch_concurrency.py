"""A batch of LLM-bound actions must not serialise into the next tick.

``process_scheduled_actions`` runs every 60s with ``max_instances=1`` and used to
execute its batch strictly one action at a time. Each action is an LLM call, so
the tick's duration is the SUM of the batch.

Measured on the production instance (373 ticks in one day): median 0.01s,
p90 0.03s — and a tail at 26.6s, 51.6s, 81.8s, 187.3s. Over the audited week
APScheduler logged 34 ``Execution of job "Process scheduled actions" skipped:
maximum number of running instances reached (1)``: every tick falling inside a
long batch is dropped, so actions due in that window wait for the next free
tick instead of firing on time.

Executing the batch concurrently makes the tick cost the SLOWEST action instead
of their sum. It is safe here because each ``execute_single_action`` opens its
OWN database session — the codebase rule is that an ``AsyncSession`` is never
shared across concurrent tasks, and this executor already satisfies it.

Concurrency stays BOUNDED and settings-driven: unbounded fan-out would replace a
scheduling delay with a burst against the LLM provider and the connection pool.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest

from src.core.config import settings
from src.infrastructure.scheduler import scheduled_action_executor as executor_module

pytestmark = pytest.mark.unit


class _Harness:
    """Replaces the DB and the per-action executor, keeping the batch logic."""

    def __init__(self, count: int) -> None:
        self.refs = [(uuid4(), uuid4()) for _ in range(count)]
        self.started = 0
        self.peak_concurrency = 0
        self._in_flight = 0
        self.executed: list[Any] = []
        self.behaviour: dict[Any, str] = {}
        self.delay = 0.0

    async def execute(self, *, action_id: Any, user_id: Any) -> Any:
        self._in_flight += 1
        self.started += 1
        self.peak_concurrency = max(self.peak_concurrency, self._in_flight)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            self.executed.append(action_id)
            outcome = self.behaviour.get(action_id, "success")
            if outcome == "raise":
                raise RuntimeError("action blew up")
            return None if outcome == "skip" else {"ok": True}
        finally:
            self._in_flight -= 1


@pytest.fixture()
def harness(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201 - pytest fixture
    def _make(count: int) -> _Harness:
        h = _Harness(count)

        class _Repo:
            def __init__(self, _db: Any) -> None: ...

            async def recover_stale_executing(self, **_kw: Any) -> int:
                return 0

            async def get_and_lock_due_actions(self, **_kw: Any) -> list[Any]:
                return [type("A", (), {"id": a, "user_id": u})() for a, u in h.refs]

        class _Db:
            async def commit(self) -> None: ...

        class _Ctx:
            async def __aenter__(self) -> Any:
                return _Db()

            async def __aexit__(self, *_a: Any) -> bool:
                return False

        import src.domains.scheduled_actions.repository as repo_module
        import src.infrastructure.database.session as session_module

        monkeypatch.setattr(repo_module, "ScheduledActionRepository", _Repo)
        monkeypatch.setattr(session_module, "get_db_context", lambda: _Ctx())
        monkeypatch.setattr(executor_module, "execute_single_action", h.execute)
        return h

    return _make


class TestTheBatchRunsConcurrently:
    """The tick must cost the slowest action, not the sum of the batch."""

    async def test_wall_clock_is_not_the_sum(self, harness: Any) -> None:
        h = harness(6)
        h.delay = 0.05

        started = asyncio.get_running_loop().time()
        stats = await executor_module.process_scheduled_actions()
        elapsed = asyncio.get_running_loop().time() - started

        assert stats["processed"] == 6
        sequential = 6 * h.delay
        assert elapsed < sequential * 0.8, (
            f"the batch took {elapsed:.3f}s for 6 actions of {h.delay}s each — still "
            f"serialised. A long batch drops the ticks that follow it (34 skips measured "
            f"in a week)."
        )

    async def test_concurrency_is_bounded_by_the_setting(self, harness: Any) -> None:
        """Unbounded fan-out trades a delay for a burst on the provider and the pool."""
        h = harness(12)
        h.delay = 0.05

        await executor_module.process_scheduled_actions()

        limit = settings.scheduled_actions_max_concurrency
        assert (
            h.peak_concurrency <= limit
        ), f"peak concurrency {h.peak_concurrency} exceeded the configured limit {limit}"
        assert h.peak_concurrency > 1, "the batch did not run concurrently at all"


class TestEveryActionIsAccountedFor:
    """Concurrency must not lose an action, nor mis-count an outcome."""

    async def test_all_actions_execute(self, harness: Any) -> None:
        h = harness(5)

        stats = await executor_module.process_scheduled_actions()

        assert len(h.executed) == 5
        assert stats["processed"] == 5
        assert stats["success"] == 5

    async def test_one_failure_does_not_abort_the_batch(self, harness: Any) -> None:
        h = harness(4)
        h.behaviour[h.refs[1][0]] = "raise"

        stats = await executor_module.process_scheduled_actions()

        assert h.started == 4, "a raising action must not cancel its siblings"
        assert stats["processed"] == 4
        assert stats["failed"] == 1
        assert stats["success"] == 3

    async def test_a_skipped_action_is_counted_as_skipped(self, harness: Any) -> None:
        h = harness(3)
        h.behaviour[h.refs[0][0]] = "skip"

        stats = await executor_module.process_scheduled_actions()

        assert stats["skipped"] == 1
        assert stats["success"] == 2
        assert stats["failed"] == 0

    async def test_an_empty_batch_returns_immediately(
        self, harness: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        h = harness(0)

        stats = await executor_module.process_scheduled_actions()

        assert stats["processed"] == 0
        assert h.started == 0
