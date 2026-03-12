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
from collections.abc import Coroutine
from typing import Any

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Global set to keep strong references to background tasks
# Prevents garbage collection while tasks are running
_background_tasks: set[asyncio.Task] = set()

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
        elif t.exception():
            logger.error(
                "background_task_failed",
                task_name=name or "unnamed",
                error=str(t.exception()),
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
    (like memory extraction) completes before the process exits.

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
            # Cancel pending tasks
            for task in pending:
                task.cancel()
        else:
            logger.info(
                "background_tasks_completed",
                count=len(done),
            )

        return task_count

    except Exception as e:
        logger.error(
            "wait_background_tasks_failed",
            error=str(e),
        )
        return 0


async def await_run_id_tasks(run_id: str, timeout: float = 5.0) -> int:
    """
    Wait for all background tasks registered for a specific run_id.

    Called in service.py before emitting the SSE done chunk to ensure
    background extraction tasks (memory, interests) have persisted their
    tokens, so the aggregated summary includes the full cost.

    Args:
        run_id: The pipeline run_id whose tasks to await
        timeout: Maximum time to wait in seconds (default 5s)

    Returns:
        Number of tasks that were awaited

    Example:
        >>> # Before querying aggregated tokens for SSE done:
        >>> awaited = await await_run_id_tasks(run_id, timeout=5.0)
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
            error=str(e),
        )

    return len(tasks)


def get_active_background_tasks_count() -> int:
    """
    Get the number of currently active background tasks.

    Useful for monitoring and debugging.

    Returns:
        Count of active background tasks
    """
    return len(_background_tasks)


def cancel_all_background_tasks() -> int:
    """
    Cancel all active background tasks.

    Use with caution - only for emergency shutdown scenarios.

    Returns:
        Number of tasks cancelled
    """
    count = len(_background_tasks)

    for task in _background_tasks:
        if not task.done():
            task.cancel()

    logger.warning(
        "background_tasks_cancelled",
        count=count,
    )

    return count
