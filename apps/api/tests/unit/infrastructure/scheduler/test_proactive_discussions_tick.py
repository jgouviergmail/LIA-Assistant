"""The elected discussion tick serves its batch under the operator's concurrency (ADR-358).

The tick's capacity is the operator's: how many owners it serves and how many runs it
drives at once are settings, and one owner's fault never stops the others.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Self
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from src.core.config import settings
from src.infrastructure.scheduler import proactive_discussions as tick

pytestmark = pytest.mark.unit


class _AcquiredLock:
    """The elected lock, already won."""

    acquired = True

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


class _NoRebuildSession:
    """A session in which no owner asked for a rebuild."""

    async def scalar(self, statement: object) -> None:
        return None


@asynccontextmanager
async def _session() -> AsyncIterator[_NoRebuildSession]:
    yield _NoRebuildSession()


async def test_the_tick_runs_its_batch_under_the_configured_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owners = tuple(uuid4() for _ in range(6))
    monkeypatch.setattr(settings, "proactive_discussions_enabled", True)
    monkeypatch.setattr(settings, "discussion_tick_concurrency", 3)
    monkeypatch.setattr(tick, "configured_limits", lambda: object())
    monkeypatch.setattr(tick, "SchedulerLock", _AcquiredLock)
    monkeypatch.setattr(tick, "get_redis_cache", AsyncMock())
    monkeypatch.setattr(tick, "maintain_discussion_context", AsyncMock())
    monkeypatch.setattr(tick, "dispatch_pending_discussions", AsyncMock())
    monkeypatch.setattr(tick, "get_db_context", _session)
    monkeypatch.setattr(
        tick, "SpendRepository", lambda db: SimpleNamespace(recover_expired=AsyncMock())
    )
    monkeypatch.setattr(tick, "select_owners", AsyncMock(return_value=owners))
    running = peak = 0

    async def run(owner: UUID, *, rebuild_epoch: int | None) -> str:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1
        if owner == owners[0]:
            raise RuntimeError("one owner's fault")
        return "completed"

    monkeypatch.setattr(tick, "run_for_owner", run)

    result = await tick.process_proactive_discussions()

    assert peak == 3
    assert result == {"processed": 6, "completed": 5, "failed": 1}
