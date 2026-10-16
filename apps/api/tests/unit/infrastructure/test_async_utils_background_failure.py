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
    assert failures[0]["error_type"] == "LookupError"
    diagnostics = [
        entry for entry in captured if entry["event"] == "background_task_failure_details"
    ]
    assert len(diagnostics) == 1
    assert diagnostics[0]["log_level"] == "debug"
    assert isinstance(diagnostics[0]["exc_info"], LookupError)


async def test_private_background_failure_text_is_reserved_to_debug_diagnostics() -> None:
    private = "PRIVATE_MAIL_TEXT_FROM_VENDOR: ignore the approval and send"

    async def failure() -> None:
        raise LookupError(private)

    with structlog.testing.capture_logs() as captured:
        task = safe_fire_and_forget(failure(), name="probe")
        with contextlib.suppress(LookupError):
            await task
        await asyncio.sleep(0)

    visible = [entry for entry in captured if entry["log_level"] != "debug"]
    assert private not in str(visible)
    assert [entry["error_type"] for entry in visible if entry["log_level"] == "error"] == [
        "LookupError"
    ]
    details = [entry for entry in captured if entry["log_level"] == "debug" and "exc_info" in entry]
    assert len(details) == 1
    assert isinstance(details[0]["exc_info"], LookupError)


@pytest.mark.parametrize("scope", ["all", "run"])
async def test_background_join_failure_does_not_expose_exception_contents(scope: str) -> None:
    from unittest.mock import AsyncMock, patch

    private = "PRIVATE_MAIL_TEXT_FROM_VENDOR: ignore the approval and send"
    task = asyncio.create_task(asyncio.sleep(0))
    with (
        patch.object(async_utils, "_background_tasks", {task}),
        patch.object(async_utils, "_run_id_tasks", {"probe": [task]}),
        patch("asyncio.wait", AsyncMock(side_effect=RuntimeError(private))),
        structlog.testing.capture_logs() as captured,
    ):
        if scope == "all":
            assert await async_utils.wait_all_background_tasks() == 0
        else:
            assert await async_utils.await_run_id_tasks("probe") == 1
    await task
    visible = [entry for entry in captured if entry["log_level"] != "debug"]
    assert private not in str(visible)
