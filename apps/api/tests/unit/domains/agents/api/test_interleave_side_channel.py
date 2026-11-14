"""The stream ends before the turn does (double write of a cancelled turn, 2026-11-05).

The pump that reads the stream runs in a task of its own. Cancelled and left behind, it
closed the stream while the turn went on closing itself: the two ends raced on the
tracker, and a turn's spend was written twice.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import suppress
from unittest.mock import patch

import pytest

from src.domains.agents.api.service import AgentService

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def _read(stream: AsyncGenerator[tuple[str, str]], ended: list[str]) -> None:
    try:
        async for _ in AgentService._interleave_side_channel(
            stream, asyncio.Queue(), poll_interval=0.01
        ):
            pass
    finally:
        ended.append("turn")


async def test_a_cancelled_turn_waits_for_its_stream_to_end() -> None:
    ended: list[str] = []

    async def stream() -> AsyncGenerator[tuple[str, str]]:
        try:
            await asyncio.sleep(60)
            yield "never", ""
        finally:
            await asyncio.sleep(0.02)  # its spend being written
            ended.append("stream")

    turn = asyncio.create_task(_read(stream(), ended))
    await asyncio.sleep(0.03)
    turn.cancel()
    with suppress(asyncio.CancelledError):
        await turn

    assert ended == ["stream", "turn"]


async def test_a_stream_that_never_ends_does_not_hold_the_turn() -> None:
    ended: list[str] = []
    stuck = asyncio.Event()

    async def stream() -> AsyncGenerator[tuple[str, str]]:
        try:
            await asyncio.sleep(60)
            yield "never", ""
        finally:
            await stuck.wait()

    with patch("src.domains.agents.api.stream_pump.STREAM_TEARDOWN_WAIT_SECONDS", 0.02):
        turn = asyncio.create_task(_read(stream(), ended))
        await asyncio.sleep(0.03)
        turn.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.wait_for(turn, timeout=1)

    assert ended == ["turn"]
    stuck.set()
    await asyncio.sleep(0)


async def test_a_stream_ended_by_its_own_failure_leaves_nothing_unread() -> None:
    """Its exception is read here: an unread one is a test failure and log noise."""

    async def stream() -> AsyncGenerator[tuple[str, str]]:
        try:
            await asyncio.sleep(60)
            yield "never", ""
        finally:
            raise RuntimeError("closing failed")

    ended: list[str] = []
    turn = asyncio.create_task(_read(stream(), ended))
    await asyncio.sleep(0.03)
    turn.cancel()
    with suppress(asyncio.CancelledError):
        await turn

    assert ended == ["turn"]


async def test_a_stream_that_finishes_is_read_to_its_end() -> None:
    async def stream() -> AsyncGenerator[tuple[str, str]]:
        yield "first", "a"
        yield "second", "b"

    read = [
        item
        async for item in AgentService._interleave_side_channel(
            stream(), asyncio.Queue(), poll_interval=0.01
        )
    ]

    assert read == [("first", "a"), ("second", "b")]
