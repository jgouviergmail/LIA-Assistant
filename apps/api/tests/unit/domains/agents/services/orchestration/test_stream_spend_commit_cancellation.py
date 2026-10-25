"""A turn cancelled while its tracked spend is written ends cancelled (2026-10-25).

``execute_graph_stream`` commits the turn's tracker in its ``finally``: model
calls that happened and were billed (ADR-117). The commit was shielded, and a
cancellation landing during it was logged as « completed » — it was not,
``shield`` does not wait — and swallowed: the generator ended normally and the
turn ran on past its stream. The commit now runs to its end, then the
cancellation reaches the task consuming the stream.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest

from src.domains.agents.models import create_initial_state
from src.domains.agents.services.orchestration import service as orchestration_module
from src.domains.agents.services.orchestration import turn_input
from src.domains.agents.services.orchestration.service import OrchestrationService

pytestmark = pytest.mark.unit


class _GatedTracker:
    """A tracker whose commit the test holds open, then releases."""

    def __init__(self, failure: Exception | None = None) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.committed = asyncio.Event()
        self.commits = 0
        self._failure = failure

    async def commit(self) -> None:
        self.commits += 1
        self.started.set()
        await self.release.wait()
        if self._failure is not None:
            raise self._failure
        self.committed.set()


class _OneChunkGraph:
    """A graph whose stream yields one chunk, then completes."""

    async def astream(
        self, *_args: object, **_kwargs: object
    ) -> AsyncIterator[tuple[str, dict[str, object]]]:
        yield ("values", {})


@pytest.fixture
def bare_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    """The stream's collaborators reduced to nothing: only its ``finally`` is under test."""

    async def no_store() -> None:
        return None

    async def same_context(context: object) -> object:
        return context

    monkeypatch.setattr(orchestration_module, "get_tool_context_store", no_store)
    monkeypatch.setattr(
        orchestration_module, "enrich_config_with_callbacks", lambda config, **_kw: config
    )
    monkeypatch.setattr(orchestration_module, "build_runtime_context", lambda **_kw: object())
    monkeypatch.setattr(orchestration_module, "with_current_extraction_revision", same_context)
    monkeypatch.setattr(turn_input, "prepare_graph_input", lambda *_a: {})


async def _consume(tracker: _GatedTracker, ran_on: list[str]) -> None:
    user_id = uuid4()
    async for _mode, _chunk in OrchestrationService().execute_graph_stream(
        graph=_OneChunkGraph(),
        state=create_initial_state(user_id, "session", "run"),
        conversation_id=uuid4(),
        user_id=user_id,
        session_id="session",
        run_id="run",
        tool_deps=None,
        tracker=tracker,
    ):
        pass
    ran_on.append("the turn ran on past its stream")


@pytest.mark.usefixtures("bare_stream")
async def test_a_cancellation_during_the_spend_commit_reaches_the_stream_task() -> None:
    tracker = _GatedTracker()
    ran_on: list[str] = []
    task = asyncio.create_task(_consume(tracker, ran_on))
    await tracker.started.wait()

    task.cancel()
    for _ in range(3):
        await asyncio.sleep(0)
    tracker.release.set()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert ran_on == []
    assert tracker.committed.is_set(), "the spend is written before the cancellation propagates"
    assert tracker.commits == 1


@pytest.mark.usefixtures("bare_stream")
async def test_a_failed_spend_commit_never_breaks_the_stream() -> None:
    tracker = _GatedTracker(failure=RuntimeError("ledger unavailable"))
    tracker.release.set()
    ran_on: list[str] = []

    await _consume(tracker, ran_on)

    assert ran_on == ["the turn ran on past its stream"]
