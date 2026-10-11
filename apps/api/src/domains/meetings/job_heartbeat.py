"""Keep regeneration ownership live and cancel work after a lost heartbeat."""

import asyncio
from collections.abc import Awaitable, Callable


async def run_with_heartbeats[T](
    work: Callable[[], Awaitable[T]],
    heartbeat: Callable[[], Awaitable[None]],
    interval_seconds: float,
) -> T:
    await heartbeat()
    task = asyncio.ensure_future(work())

    async def pulse() -> None:
        while True:
            await asyncio.sleep(interval_seconds)
            await heartbeat()

    timer = asyncio.create_task(pulse(), name="meeting_job_heartbeat")
    try:
        completed, _ = await asyncio.wait((task, timer), return_when=asyncio.FIRST_COMPLETED)
        if timer in completed:
            timer.result()
        result = await task
        await heartbeat()
        return result
    finally:
        timer.cancel()
        task.cancel()
        await asyncio.gather(timer, task, return_exceptions=True)
