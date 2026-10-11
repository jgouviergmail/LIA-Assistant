"""Finish a bounded live-file step before cancellation can release its owner/staging lifetime."""

import asyncio
from collections.abc import Callable


async def finish_disk_step(operation: Callable[[], None]) -> bool:
    """Execute once; return whether the caller must propagate cancellation afterward.

    Cancelling an asyncio waiter does not stop a filesystem worker. Rollback,
    staging cleanup and release of the owner lock must wait for that worker.
    Repeated cancellation waits for the same task and never starts another write.
    """
    task = asyncio.create_task(asyncio.to_thread(operation))
    cancelled = False
    while True:
        try:
            await asyncio.shield(task)
            return cancelled
        except asyncio.CancelledError:
            cancelled = True
            if task.done():
                task.result()
                return True


async def run_disk_step(operation: Callable[[], None]) -> None:
    """Finish an owned disk step, then propagate any requested cancellation."""
    if await finish_disk_step(operation):
        raise asyncio.CancelledError


async def read_disk_step[Value](operation: Callable[[], Value]) -> Value:
    """Return one worker result only after its staging lifetime can safely end."""
    result: list[Value] = []

    def read() -> None:
        result.append(operation())

    await run_disk_step(read)
    return result[0]
