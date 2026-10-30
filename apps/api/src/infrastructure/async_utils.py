"""
Async Utilities for FastAPI/LangGraph.

Provides safe patterns for background task execution that avoid
common pitfalls with asyncio in web frameworks.

Key utilities:
- safe_fire_and_forget: Launch background tasks without GC issues
- wait_all_background_tasks: Graceful shutdown support

Problem:
    In FastAPI, using raw asyncio.create_task() can lead to tasks being
    garbage collected if the HTTP request completes before the task.
    This is because Python's GC may collect the Task object if no strong
    reference is held.

Solution:
    Keep strong references to all background tasks in a global set.
    Remove them via done callback when they complete.

Example:
    >>> safe_fire_and_forget(extract_memories_background(store, user_id, messages))
    >>> # Task runs in background, survives HTTP request completion
"""

import asyncio
from collections.abc import Awaitable, Callable, Collection, Coroutine, Sequence
from typing import Any, Final

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Global set to keep strong references to background tasks
# Prevents garbage collection while tasks are running
_background_tasks: set[asyncio.Task] = set()

# How long a shutdown waits for the tasks it CANCELLED to finish their cancellation
# (audit A05): what a cancellation runs — a finally releasing a claim, closing a file,
# writing a final status — needs the loop, and the pools it uses close right after.
# Counted in the stop budget (test_graceful_shutdown_budget_guard.py).
BACKGROUND_TASKS_CANCEL_JOIN_TIMEOUT_S: Final[float] = 5.0

# Per-run_id registry for tasks that should be awaited before SSE done chunk.
# Enables the SSE done event to include tokens from background extraction tasks
# (memory, interests) by waiting for them before querying aggregated totals.
_run_id_tasks: dict[str, list[asyncio.Task]] = {}


def safe_fire_and_forget(
    coro: Coroutine[Any, Any, Any],
    name: str | None = None,
    run_id: str | None = None,
) -> asyncio.Task:
    """
    Launch a coroutine in the background safely.

    Avoids the FastAPI garbage collection issue where asyncio.create_task()
    can be GC'd if the HTTP request terminates before the task completes.

    How it works:
    1. Creates an asyncio Task from the coroutine
    2. Adds task to global set (strong reference prevents GC)
    3. Registers a done callback to remove task from set when complete
    4. Logs any exceptions from the background task

    Args:
        coro: The coroutine to execute in background
        name: Optional name for logging/debugging
        run_id: Optional run_id to register task for later awaiting.
            When provided, the task is tracked so that ``await_run_id_tasks(run_id)``
            can wait for it before emitting the SSE done chunk.

    Returns:
        The created Task (for monitoring if needed)

    Example:
        >>> safe_fire_and_forget(
        ...     extract_memories_background(store, user_id, messages),
        ...     name="memory_extraction",
        ...     run_id="3dd39222-4619-4f74-b0b8-c9d757d1d996",
        ... )
    """
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)

    # Register for per-run_id awaiting (token aggregation before SSE done)
    if run_id:
        _run_id_tasks.setdefault(run_id, []).append(task)

    def _on_task_done(t: asyncio.Task) -> None:
        """Callback when task completes."""
        _background_tasks.discard(t)

        # Log any exceptions
        if t.cancelled():
            logger.debug("background_task_cancelled", task_name=name or "unnamed")
        elif (error := t.exception()) is not None:
            # Keep the diagnostic traceback, but reserve private exception
            # contents to DEBUG rather than visible operational events.
            logger.error(
                "background_task_failed",
                task_name=name or "unnamed",
                error_type=type(error).__name__,
            )
            logger.debug(
                "background_task_failure_details",
                task_name=name or "unnamed",
                exc_info=error,
            )
        else:
            logger.debug("background_task_completed", task_name=name or "unnamed")

    task.add_done_callback(_on_task_done)

    logger.debug(
        "background_task_started",
        task_name=name or "unnamed",
        run_id=run_id,
        active_tasks=len(_background_tasks),
    )

    return task


async def wait_all_background_tasks(timeout: float = 30.0) -> int:
    """
    Wait for all background tasks to complete.

    Useful for graceful shutdown to ensure all background work
    (like memory extraction) completes before the process exits. Tasks still
    running at ``timeout`` are cancelled, then JOINED for at most
    ``BACKGROUND_TASKS_CANCEL_JOIN_TIMEOUT_S`` so their cancellation runs before
    the shutdown closes what it needs; one that will not stop is named.

    Args:
        timeout: Maximum time to wait in seconds (default 30s)

    Returns:
        Number of tasks that were waited on

    Example:
        >>> # In FastAPI lifespan shutdown:
        >>> @asynccontextmanager
        >>> async def lifespan(app: FastAPI):
        ...     yield
        ...     await wait_all_background_tasks(timeout=30.0)
    """
    if not _background_tasks:
        return 0

    task_count = len(_background_tasks)
    logger.info(
        "waiting_for_background_tasks",
        count=task_count,
        timeout=timeout,
    )

    try:
        done, pending = await asyncio.wait(
            _background_tasks,
            timeout=timeout,
        )

        if pending:
            logger.warning(
                "background_tasks_timeout",
                completed=len(done),
                pending=len(pending),
            )
            # Cancel pending tasks, then join them: a cancellation is a request, and
            # returning before it ran let the shutdown close what its cleanup needs.
            for task in pending:
                task.cancel()
            _, unjoined = await asyncio.wait(
                pending, timeout=BACKGROUND_TASKS_CANCEL_JOIN_TIMEOUT_S
            )
            if unjoined:
                logger.warning(
                    "background_tasks_not_joined",
                    count=len(unjoined),
                    task_names=sorted(task.get_name() for task in unjoined),
                )
        else:
            logger.info(
                "background_tasks_completed",
                count=len(done),
            )

        return task_count

    except Exception as e:
        logger.error(
            "wait_background_tasks_failed",
            error_type=type(e).__name__,
        )
        logger.debug("wait_background_tasks_failure_details", exc_info=e)
        return 0


async def await_run_id_tasks(run_id: str, timeout: float = 15.0) -> int:
    """
    Wait for all background tasks registered for a specific run_id.

    Called in service.py before emitting the SSE done chunk to ensure
    background extraction tasks (memory, interests) have persisted their
    tokens, so the aggregated summary includes the full cost.

    Args:
        run_id: The pipeline run_id whose tasks to await
        timeout: Maximum time to wait in seconds (default 15s).
            Increased from 5s to 15s to accommodate RPi5 latency
            on background LLM calls (memory, interest, journal extraction).

    Returns:
        Number of tasks that were awaited

    Example:
        >>> # Before querying aggregated tokens for SSE done:
        >>> awaited = await await_run_id_tasks(run_id, timeout=15.0)
        >>> summary = await temp_tracker.get_aggregated_summary_dto_from_db()
    """
    tasks = _run_id_tasks.pop(run_id, [])
    if not tasks:
        return 0

    # Filter out already-completed tasks
    pending = [t for t in tasks if not t.done()]
    if not pending:
        return len(tasks)

    try:
        done, timed_out = await asyncio.wait(pending, timeout=timeout)
        if timed_out:
            logger.warning(
                "run_id_tasks_timeout",
                run_id=run_id,
                completed=len(done),
                timed_out=len(timed_out),
                timeout=timeout,
            )
        else:
            logger.debug(
                "run_id_tasks_completed",
                run_id=run_id,
                count=len(done),
            )
    except Exception as e:
        logger.error(
            "run_id_tasks_await_failed",
            run_id=run_id,
            error_type=type(e).__name__,
        )
        logger.debug("run_id_tasks_await_failure_details", run_id=run_id, exc_info=e)

    return len(tasks)


def get_active_background_tasks_count() -> int:
    """
    Get the number of currently active background tasks.

    Useful for monitoring and debugging.

    Returns:
        Count of active background tasks
    """
    return len(_background_tasks)


def _report_cancelled_write_failure(task: asyncio.Future[None], label: str) -> None:
    """Retrieve a late failure and report its type without private exception text."""
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        logger.error(f"{label}_failed_after_cancellation", error_type=type(error).__name__)
        logger.debug(f"{label}_failure_details", exc_info=error)


async def write_through_cancellation(
    make_write: Callable[[], Awaitable[None]],
    *,
    attempts: int,
    label: str,
) -> bool:
    """Run one write to completion even while the caller is being cancelled.

    The problem it solves is narrow and was measured, twice. A durable write in
    a ``finally`` block runs while a cancellation is already propagating, so a
    plain ``await`` is cut short and the row is lost. ``asyncio.shield`` fixes
    that for the FIRST delivery — but a cancellation can be re-delivered, and
    the naive retry then calls the write AGAIN.

    Simulated 2026-09-04: shielding a fresh coroutine per attempt produced
    ``['start', 'start', 'done', 'done']`` — one turn's row upserted twice, its
    ``segments`` counter reading 2 for a turn nobody interrupted. So the work
    becomes a TASK once, and every attempt awaits that same task.

    ``make_write`` is a factory rather than an awaitable for the codebase's
    standing reason (Systemic Rules): a coroutine is awaitable exactly once, so
    a seam holding one cannot decide whether to run it.

    Args:
        make_write: Builds the write. Called exactly once.
        attempts: How many re-deliveries to survive before letting the task
            finish on its own. Bounded so a shutdown is never held open.
        label: Event name for the abandonment log.

    Returns:
        True when a cancellation was delivered. The caller re-raises it: a
        cancelled turn must stay cancelled — writing a register never
        resurrects it.
    """
    if attempts < 1:
        raise ValueError("At least one cancellation grace attempt is required.")
    task = asyncio.ensure_future(make_write())
    task.set_name(label)
    # asyncio holds tasks WEAKLY, and the abandonment path below returns while
    # this one is still running — its only local reference dies with the frame.
    # The module's own registry is what keeps a background write alive, so the
    # write uses it rather than trusting the loop.
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    cancelled = False
    for _ in range(attempts):
        try:
            # wait never cancels the inner task. Unlike shield on Python 3.14,
            # it also does not route a late private exception to asyncio's
            # ERROR handler before this helper can classify it.
            await asyncio.wait({task})
            break
        except asyncio.CancelledError:
            cancelled = True
            if task.done():
                break
    else:
        # Still writing after the last attempt: let it finish on its own rather
        # than hold the shutdown. The registry above is what keeps it alive,
        # and ``wait_all_background_tasks`` is what gives it a last chance at
        # exit — being in that set is the difference between « finishes later »
        # and « collected mid-write ».
        logger.warning(f"{label}_abandoned")
    if cancelled:
        if task.done():
            _report_cancelled_write_failure(task, label)
        else:
            task.add_done_callback(lambda done: _report_cancelled_write_failure(done, label))
    else:
        # A failure still reaches a caller that has not been stopped.
        task.result()
    return cancelled


def settled_or_raise(results: Sequence[object], *, quiet: Collection[int] = ()) -> list[Any]:
    """The answers of a ``gather(..., return_exceptions=True)``, the first failure raised.

    Every sibling settled before this reads them: a fail-fast ``gather`` raised at the
    first failure and left the others running past the act that owned them — their spend
    appended to an exited tracker, their client closed under them (briefing review B3).

    Args:
        results: What the gather returned, in its order.
        quiet: Positions whose failure stands for « nothing » (``None``) instead of raising.

    Returns:
        The answers, a quiet failure read as ``None``.

    Raises:
        BaseException: The first failure outside ``quiet``, as it was raised.
    """
    for position, result in enumerate(results):
        if isinstance(result, BaseException) and position not in quiet:
            raise result
    return [None if isinstance(result, BaseException) else result for result in results]
