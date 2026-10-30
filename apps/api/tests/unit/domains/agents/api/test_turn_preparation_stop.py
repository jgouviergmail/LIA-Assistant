"""Stopping the turn's own futures never swallows a cancellation of the turn itself.

``_stop`` cancels a future the turn started and waits for it to settle. It used to
suppress ``CancelledError`` around that wait — which is also how a cancellation of the
TURN arrives, so a person leaving while a preparation was being stopped went unheard.
"""

from __future__ import annotations

import asyncio

import pytest

from src.domains.agents.api.turn_preparation import _stop, release_each

pytestmark = pytest.mark.unit


async def test_a_cancellation_of_the_turn_is_never_swallowed() -> None:
    settling = asyncio.Event()

    async def slow_to_settle() -> None:
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            settling.set()
            await asyncio.sleep(0.2)  # its own cleanup, before it settles
            raise

    pending = asyncio.ensure_future(slow_to_settle())
    await asyncio.sleep(0)
    turn = asyncio.ensure_future(_stop(pending))
    await settling.wait()
    turn.cancel()  # the person leaves while the turn stops its preparation

    with pytest.raises(asyncio.CancelledError):
        await turn
    await asyncio.wait({pending})
    assert pending.cancelled()


async def test_a_stopped_future_settles_before_stop_returns() -> None:
    async def forever() -> None:
        await asyncio.sleep(3600)

    pending = asyncio.ensure_future(forever())
    await asyncio.sleep(0)

    await _stop(pending)

    assert pending.cancelled()


async def test_a_failed_close_never_skips_the_next_one() -> None:
    """A turn the person left releases every pooled client, whatever failed before it."""
    closed: list[str] = []

    async def voice() -> None:
        raise RuntimeError("voice close failed")

    async def tools() -> None:
        closed.append("tools")

    await release_each(voice, tools)

    assert closed == ["tools"]


async def test_a_reader_leaving_during_preparation_closes_it_in_its_own_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh review m2: closing the notices left the preparation's own generator to the
    loop's finalizer, so its cleanup (cancel the build, the pending read) ran later, in
    another task — the pattern the stream's own closing fix removed."""
    from src.domains.agents.api import turn_preparation

    closed_in: list[asyncio.Task[object] | None] = []

    async def preparation(*_a: object, **_k: object):  # type: ignore[no-untyped-def]
        try:
            yield "notice"
            await asyncio.sleep(3600)
        finally:
            closed_in.append(asyncio.current_task())

    monkeypatch.setattr(turn_preparation, "iter_mcp_preparation", preparation)
    monkeypatch.setattr(turn_preparation, "notices_reach_the_person", lambda _session: True)
    mcp = turn_preparation.MCPPreparation(
        __import__("uuid").uuid4(), run_id="r", live_session_id=None
    )
    notices = mcp.notices()

    assert await anext(notices) == "notice"
    await notices.aclose()

    assert closed_in == [asyncio.current_task()]
