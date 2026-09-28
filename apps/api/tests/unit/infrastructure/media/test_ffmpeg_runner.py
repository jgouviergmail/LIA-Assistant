"""The subprocess runner bounds every audio tool: exit codes, timeouts, cancellation.

These tests drive their own event loop rather than the suite's: on Windows the
suite runs a SelectorEventLoop (psycopg needs it), and that loop cannot spawn a
subprocess at all. A Proactor loop can; Linux's default loop can too.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable, Coroutine
from typing import Any

import pytest

from src.infrastructure.media import ffmpeg
from src.infrastructure.media.ffmpeg import FfmpegError

pytestmark = pytest.mark.unit


def _subprocess_loop() -> Callable[[], asyncio.AbstractEventLoop] | None:
    if sys.platform == "win32":
        return asyncio.ProactorEventLoop
    return None


def run_loop[T](body: Callable[[], Coroutine[Any, Any, T]]) -> T:
    """Run ``body`` on a loop that can spawn subprocesses, on every platform."""
    return asyncio.run(body(), loop_factory=_subprocess_loop())


async def run_python(code: str, *, timeout_s: float = 10.0, stdin: bytes | None = None) -> bytes:
    # The runner is program-agnostic: a Python child exercises it without ffmpeg.
    return await ffmpeg._run(sys.executable, ["-c", code], timeout_s=timeout_s, input_bytes=stdin)


def test_stdout_is_returned_and_stdin_fed() -> None:
    out = run_loop(
        lambda: run_python(
            "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read()[::-1])", stdin=b"abc"
        )
    )
    assert out == b"cba"


def test_a_failure_carries_a_bounded_stderr_excerpt() -> None:
    with pytest.raises(FfmpegError, match="exit 3") as caught:
        run_loop(lambda: run_python("import sys; sys.stderr.write('x' * 5000); sys.exit(3)"))
    assert str(caught.value).rsplit(": ", 1)[1] == "x" * ffmpeg._STDERR_EXCERPT_CHARS


def test_a_timeout_kills_the_process() -> None:
    with pytest.raises(FfmpegError, match="timed out"):
        run_loop(lambda: run_python("import time; time.sleep(30)", timeout_s=0.5))


@pytest.fixture
def spawned(monkeypatch: pytest.MonkeyPatch) -> list[asyncio.subprocess.Process]:
    """Every process the runner starts, kept for the test to inspect."""
    started: list[asyncio.subprocess.Process] = []
    real = asyncio.create_subprocess_exec

    async def spy(program: str, *args: str, **kwargs: Any) -> asyncio.subprocess.Process:
        proc = await real(program, *args, **kwargs)
        started.append(proc)
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)
    return started


async def cancel_once_started(
    code: str, spawned: list[asyncio.subprocess.Process], *, running_s: float = 0.0
) -> None:
    task = asyncio.create_task(run_python(code, timeout_s=60))
    for _ in range(250):
        if spawned:
            break
        await asyncio.sleep(0.02)
    await asyncio.sleep(running_s)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_a_cancelled_caller_does_not_leave_the_process_running(
    spawned: list[asyncio.subprocess.Process],
) -> None:
    run_loop(lambda: cancel_once_started("import time; time.sleep(30)", spawned))
    assert spawned and spawned[0].returncode is not None, "the child was reaped, not left running"


#: A child that writes until it is killed: whatever it wrote last is still in
#: the pipe when it dies.
_WRITES_FOR_EVER = (
    "import sys, itertools; "
    "[sys.stdout.write('x' * 65536) or sys.stdout.flush() for _ in itertools.count()]"
)


@pytest.mark.parametrize("gives_up", ["cancelled", "timed_out"])
def test_a_run_given_up_closes_its_pipes_before_returning(
    spawned: list[asyncio.subprocess.Process], gives_up: str
) -> None:
    """Killed and reaped is not enough: a pipe left unread outlives the call.

    Measured on the Windows proactor: after ``kill`` then ``wait``, the pipes of
    a child still writing were never at their end when the call returned (0 runs
    in 10, cancelled or timed out), and an open pipe was reported unclosed once
    the loop that owned it had gone (a teardown error of the fast suite).
    """

    async def body() -> None:
        if gives_up == "cancelled":
            await cancel_once_started(_WRITES_FOR_EVER, spawned, running_s=0.2)
        else:
            with pytest.raises(FfmpegError, match="timed out"):
                await run_python(_WRITES_FOR_EVER, timeout_s=0.3)
        # Checked where the runner handed control back — before the loop could
        # run any callback that would close them later.
        (proc,) = spawned
        assert proc.stdout is not None and proc.stdout.at_eof()
        assert proc.stderr is not None and proc.stderr.at_eof()
        assert proc.returncode is not None

    run_loop(body)


def test_a_missing_binary_is_named() -> None:
    with pytest.raises(FfmpegError, match="not installed"):
        run_loop(lambda: ffmpeg._run("definitely-not-a-binary-lia", [], timeout_s=5))
