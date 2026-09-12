"""The worker memory sampler has one owner: started in the lifespan, cancelled at shutdown."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest

from src.infrastructure.startup import observability, shutdown

pytestmark = pytest.mark.unit


async def _forever() -> None:
    await asyncio.Event().wait()


async def test_start_returns_the_running_task_bound_to_the_configured_interval() -> None:
    captured: dict[str, Any] = {}

    async def fake_sampler(interval: float, **kwargs: Any) -> None:
        captured["interval"] = interval
        await _forever()

    with (
        patch(
            "src.infrastructure.observability.process_memory.sample_worker_memory",
            fake_sampler,
        ),
        patch.object(observability.settings, "worker_memory_sample_interval", 7),
    ):
        task = observability.start_worker_memory_sampler()
        await asyncio.sleep(0)

    assert task is not None and not task.done()
    assert captured["interval"] == 7
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_shutdown_cancels_the_sampler_it_was_handed() -> None:
    task = asyncio.create_task(_forever())
    await asyncio.sleep(0)

    await shutdown.stop_worker_memory_sampler(task)

    assert task.cancelled()


async def test_shutdown_tolerates_a_sampler_that_never_started() -> None:
    await shutdown.stop_worker_memory_sampler(None)


def test_the_handles_carry_the_sampler_to_shutdown() -> None:
    assert "worker_memory_task" in shutdown.StartupHandles.__dataclass_fields__


async def test_shutdown_survives_a_sampler_that_died_on_its_own() -> None:
    async def broken() -> None:
        raise ValueError("unreadable status file")

    task = asyncio.create_task(broken())
    await asyncio.sleep(0)

    await shutdown.stop_worker_memory_sampler(task)  # must not raise
