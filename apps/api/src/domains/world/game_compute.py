"""Bounded process-local CPU admission; no queued per-match task and no work under SQL/CAS.

A search whose caller gave up at the deadline keeps running — a thread cannot be
cancelled — but it holds its slot until it returns, so the worker never runs more
than its bound. Those searches belong to this module: ``drain_game_compute`` is
awaited by the shutdown sequence before the event loop and its executor close.
"""

import asyncio
import time

import structlog

from src.core.config import settings
from src.core.constants import WORLD_ARCADE_BOT_CONCURRENCY
from src.domains.world.game_commands import GameCommand
from src.domains.world.game_context import GameScope
from src.domains.world.game_preparation import PreparedGame, can_prepare, prepare_game
from src.domains.world.schemas import WorldState
from src.infrastructure.observability.metrics_world import (
    world_game_compute_fallback_total,
    world_game_compute_seconds,
)

_slots = asyncio.Semaphore(WORLD_ARCADE_BOT_CONCURRENCY)
_running: set[asyncio.Task[PreparedGame | None]] = set()
logger = structlog.get_logger(__name__)


def _completed(task: asyncio.Task[PreparedGame | None]) -> None:
    """Own timed-out task completion too; never leak an unobserved task exception."""
    _running.discard(task)
    if not task.cancelled() and task.exception() is not None:
        logger.error("world_game_compute_failed", error_type=type(task.exception()).__name__)


async def _compute(
    state: WorldState, scope: GameScope, command: GameCommand
) -> PreparedGame | None:
    """The deterministic engine itself charges every child against its hard node cap."""
    return await asyncio.to_thread(prepare_game, state, scope, command)


async def _run(state: WorldState, scope: GameScope, command: GameCommand) -> PreparedGame | None:
    """Release CPU admission only when the actual thread has returned, including after caller timeout."""
    try:
        return await _compute(state, scope, command)
    finally:
        _slots.release()


async def prepare_bounded(
    state: WorldState, scope: GameScope, command: GameCommand
) -> PreparedGame | None:
    """Use an immediate legal fallback on saturation or deadline; never create an unbounded work queue.

    Args:
        state: Observed authority, read before the commit.
        scope: The commanding account and controller generation.
        command: The solo move or solo rematch to answer.

    Returns:
        The sealed preparation (a searched answer, or the legal fallback when the
        worker is busy or the deadline passed), or None when none is needed.
    """
    if not can_prepare(state, scope, command):
        return None
    if _slots.locked():
        world_game_compute_fallback_total.labels(reason="busy").inc()
        return prepare_game(state, scope, command, 0)
    await _slots.acquire()
    task = asyncio.create_task(_run(state, scope, command), name="world_game_compute")
    _running.add(task)
    task.add_done_callback(_completed)
    started = time.monotonic()
    try:
        return await asyncio.wait_for(asyncio.shield(task), settings.world_arcade_bot_seconds)
    except TimeoutError:
        world_game_compute_fallback_total.labels(reason="deadline").inc()
        return prepare_game(state, scope, command, 0)
    finally:
        world_game_compute_seconds.observe(time.monotonic() - started)


async def drain_game_compute(timeout: float) -> int:
    """Await every search still running on this loop, then cancel what outlives the bound.

    A cancelled search stops waiting for its thread and releases its slot; the
    thread itself finishes inside the executor the loop shuts down last.

    Args:
        timeout: Seconds the running searches may take to return on their own.

    Returns:
        How many searches were still running at the bound and had to be cancelled.
    """
    pending = set(_running)
    if not pending:
        return 0
    _, late = await asyncio.wait(pending, timeout=timeout)
    for task in late:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    if late:
        logger.warning("world_game_compute_drain_cancelled", count=len(late))
    return len(late)
