"""The JEV statistics flusher has one owner: started in the lifespan, awaited at shutdown."""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infrastructure.startup import observability, shutdown

pytestmark = pytest.mark.unit


def test_start_builds_and_starts_a_flusher_bound_to_the_configured_period() -> None:
    flusher_class = MagicMock()
    with (
        patch.object(observability, "JevStatisticsFlusher", flusher_class),
        patch.object(observability.settings, "jev_statistics_flush_interval", 7),
        patch.object(observability.settings, "jev_statistics_final_flush_timeout", 1.5),
    ):
        flusher = observability.start_jev_statistics_flusher()
    flusher_class.assert_called_once_with(interval_seconds=7, final_timeout_seconds=1.5)
    assert flusher is flusher_class.return_value
    flusher_class.return_value.start.assert_called_once_with()


def test_a_flusher_that_cannot_start_does_not_stop_the_boot() -> None:
    flusher_class = MagicMock()
    flusher_class.return_value.start.side_effect = RuntimeError("no running loop")
    with patch.object(observability, "JevStatisticsFlusher", flusher_class):
        assert observability.start_jev_statistics_flusher() is None


async def test_shutdown_stops_and_awaits_the_flusher_it_was_handed() -> None:
    flusher = MagicMock()
    flusher.stop = AsyncMock(return_value=4)
    await shutdown.stop_jev_statistics_flusher(flusher)
    flusher.stop.assert_awaited_once_with()


async def test_shutdown_tolerates_a_flusher_that_never_started() -> None:
    await shutdown.stop_jev_statistics_flusher(None)


async def test_shutdown_survives_a_flusher_that_fails_to_stop() -> None:
    flusher = MagicMock()
    flusher.stop = AsyncMock(side_effect=RuntimeError("loop closed"))
    await shutdown.stop_jev_statistics_flusher(flusher)  # must not raise


def test_the_handles_carry_the_flusher_to_shutdown() -> None:
    assert "jev_statistics_flusher" in shutdown.StartupHandles.__dataclass_fields__


def test_the_last_flush_follows_every_jev_caller_and_precedes_the_pools() -> None:
    """After the drains and the JEV client, before the checkpointer and the database."""
    source = inspect.getsource(shutdown.shutdown_application)
    flush = source.index("stop_jev_statistics_flusher(")
    assert source.index("drain_chat_producers(") < flush
    assert source.index("wait_all_background_tasks(") < flush
    assert source.index("close_jev_http_client()") < flush
    assert flush < source.index("cleanup_checkpointer()")
