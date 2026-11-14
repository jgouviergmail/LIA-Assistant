"""A browser relay owns durable work; a phone relay keeps its carrier's policy."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace

from src.core.conversation_execution import ReservedWork
from src.domains.voice_sessions.session import VoiceSession
from src.infrastructure.async_utils import cancel_and_join, finish_owned_task, safe_fire_and_forget
from src.infrastructure.streaming.reservation_work import (
    finish_work,
    fork_relay,
    owned_work,
)


async def _await_start(
    task: asyncio.Task[None], started: asyncio.Future[None], work: ReservedWork
) -> None:
    """Hand ownership to a body that actually entered, or join and settle the unused task."""

    async def abandon() -> None:
        await cancel_and_join(task)
        await finish_work(work)

    try:
        try:
            await asyncio.wait({started, task}, return_when=asyncio.FIRST_COMPLETED)
        except BaseException:
            if not started.done():
                await finish_owned_task(asyncio.create_task(abandon()))
            raise
        if not started.done():
            await finish_work(work)
            task.result()
    finally:
        if not started.done():
            started.cancel()


async def schedule_session_relay(
    session: VoiceSession, body: Callable[[VoiceSession], Awaitable[None]], *, name: str
) -> None:
    """Commit the relay before spawning, so an end on another worker cannot free its target."""
    if session.reservation is None:

        async def phone_body() -> None:
            await body(session)

        safe_fire_and_forget(phone_body(), name=name)
        return
    work = await fork_relay(session.reservation)
    bound = replace(session, reservation=work)
    started: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    async def browser_body() -> None:
        async with owned_work(work):
            started.set_result(None)
            await body(bound)

    coroutine = browser_body()
    try:
        task = safe_fire_and_forget(coroutine, name=name)
    except BaseException:
        coroutine.close()
        started.cancel()
        await finish_work(work)
        raise
    await _await_start(task, started, work)
