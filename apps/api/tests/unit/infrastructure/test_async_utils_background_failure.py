"""A background task that fails leaves its traceback in the log.

``safe_fire_and_forget`` used to log ``str(exception)`` only. On 2026-09-05 the
meeting job died on a one-line ``LookupError`` whose origin (a repository
statement) took a replay to locate — the traceback would have named the line.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Iterator

import pytest
import structlog

from src.infrastructure import async_utils
from src.infrastructure.async_utils import safe_fire_and_forget
from tests.support.structlog_capture import fresh_module_logger

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _fresh_module_logger() -> Iterator[None]:
    """Keep ``capture_logs`` reliable once the application logger is frozen (full-suite runs)."""
    yield from fresh_module_logger(async_utils)


async def test_a_failed_background_task_logs_its_exception_with_a_traceback() -> None:
    async def _boom() -> None:
        raise LookupError("'stopped' is not among the defined enum values")

    with structlog.testing.capture_logs() as captured:
        task = safe_fire_and_forget(_boom(), name="meeting_process_x")
        with contextlib.suppress(LookupError):
            await task
        await asyncio.sleep(0)  # let the done-callback run

    failures = [entry for entry in captured if entry["event"] == "background_task_failed"]
    assert len(failures) == 1
    assert failures[0]["task_name"] == "meeting_process_x"
    assert isinstance(failures[0]["exc_info"], LookupError)
