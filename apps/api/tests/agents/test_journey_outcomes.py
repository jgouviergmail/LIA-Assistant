"""A chat turn that ends without an answer token says why, through the real generator.

The journey histograms are fed by ``JourneyTiming``; these tests pin the three
exits of ``AgentService._stream_with_new_services`` that end a turn before its
first answer token — the person leaving, the turn failing, the graph stopping
on a question — and the ordinary end, which observes the first token instead.
"""

from __future__ import annotations

import asyncio

import pytest
from langgraph.errors import GraphInterrupt
from prometheus_client import REGISTRY

from tests.agents.test_agent_service_stream_characterization import Harness, _router, _token


def _unanswered(outcome: str) -> float:
    return (
        REGISTRY.get_sample_value("chat_journey_unanswered_seconds_count", {"outcome": outcome})
        or 0.0
    )


def _first_tokens() -> float:
    return REGISTRY.get_sample_value("chat_journey_first_token_seconds_count") or 0.0


def _raise(exc: BaseException):
    def boom(_service: object) -> None:
        raise exc

    return boom


@pytest.mark.asyncio
async def test_answered_turn_observes_its_first_token() -> None:
    before = _first_tokens()
    harness = Harness(script=[_router("conversation"), _token("Bonjour"), _token(" !")])
    with pytest.MonkeyPatch.context() as mp:
        await harness.run(mp)
    assert _first_tokens() == before + 1


@pytest.mark.asyncio
async def test_failed_turn_is_unanswered_error() -> None:
    before = _unanswered("error")
    harness = Harness(script=[_router("actionable"), _raise(RuntimeError("graph boom"))])
    with pytest.MonkeyPatch.context() as mp:
        await harness.run(mp)
    assert isinstance(harness.raised, RuntimeError)
    assert _unanswered("error") == before + 1


@pytest.mark.asyncio
async def test_interrupt_fallback_is_unanswered_interrupted() -> None:
    before = _unanswered("interrupted")
    harness = Harness(script=[_router("actionable"), _raise(GraphInterrupt())])
    with pytest.MonkeyPatch.context() as mp:
        await harness.run(mp)
    assert _unanswered("interrupted") == before + 1


@pytest.mark.asyncio
async def test_cancelled_turn_releases_its_clients() -> None:
    """A run stopped mid-flight still closes the TTS client and the connector clients."""
    released: list[str] = []

    class RecordingDependencies:
        def __init__(self, db_session: object) -> None: ...

        async def aclose(self) -> None:
            released.append("connector_clients")

    async def recording_cleanup(self: object, *, log_close_failure: bool = True) -> None:
        released.append("voice")

    harness = Harness(script=[_router("actionable"), _raise(asyncio.CancelledError())])
    with pytest.MonkeyPatch.context() as mp, pytest.raises(asyncio.CancelledError):
        mp.setattr("src.domains.agents.api.service.ToolDependencies", RecordingDependencies)
        mp.setattr(
            "src.domains.agents.services.streaming.voice_coordinator."
            "VoiceStreamCoordinator.cleanup",
            recording_cleanup,
        )
        await harness.run(mp)
    assert released == ["voice", "connector_clients"]


@pytest.mark.asyncio
async def test_cancelled_turn_is_unanswered_cancelled() -> None:
    before = _unanswered("cancelled")
    harness = Harness(script=[_router("actionable"), _raise(asyncio.CancelledError())])
    with pytest.MonkeyPatch.context() as mp, pytest.raises(asyncio.CancelledError):
        await harness.run(mp)
    assert _unanswered("cancelled") == before + 1
