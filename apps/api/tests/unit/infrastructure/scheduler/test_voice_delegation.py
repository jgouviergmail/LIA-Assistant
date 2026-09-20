"""The server-side delegation bridge: a voice's request becomes a chat turn (ADR-301).

Mirror of the browser bridge (``lib/live/delegation.ts``), proven against a
FAKE engine: an empty request costs nothing, the newest request wins (the
running turn is cancelled, the old caller hears « superseded »), an answer
comes back flattened and bounded with its delivery note, a question LIA asked
IS the result and the next request resumes that run, a wait past the vendor's
bound leaves the turn running in the thread, a busy conversation is named,
and no failure ever reaches the voice as an exception.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest

import src.infrastructure.scheduler.voice_delegation as bridge
from src.core.config import settings
from src.domains.voice_sessions.session import VoiceSession
from src.infrastructure.scheduler.out_of_turn_run import (
    RunContext,
    RunOutcome,
    RunResult,
    TurnInterrupt,
)
from src.infrastructure.scheduler.voice_delegation import (
    DelegationOutcome,
    DelegationRequest,
    delegate,
)

pytestmark = pytest.mark.unit


class FakeRedis:
    """The two verbs the bridge uses on the newest-request marker."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def set(self, key: str, value: str, ex: int | None = None, **_: Any) -> bool:
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    async def get(self, key: str) -> str | None:
        return self.store.get(key)


def _session(*, call_id: uuid.UUID | None = None) -> VoiceSession:
    return VoiceSession.phone(
        call_id=call_id or uuid.uuid4(),
        mode="delegated",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        language="fr",
        timezone="Europe/Paris",
    )


def _context() -> RunContext:
    return RunContext(
        user=object(),
        language="fr",
        timezone="Europe/Paris",
        display_name="Alex",
        display_mode="cards",
        execution_mode="react",
        memory_enabled=True,
        journals_enabled=False,
        psyche_enabled=True,
    )


def _request(
    session: VoiceSession, text: str = "Rappelle-moi la banque demain", **overrides: Any
) -> DelegationRequest:
    base: dict[str, Any] = {
        "session": session,
        "request_id": "call-1",
        "request": text,
        "spoken_text": "rappelle moi la banque demain",
        "wait_seconds": 5.0,
    }
    base.update(overrides)
    return DelegationRequest(**base)


class Rig:
    """The bridge's seams, patched by name: the engine, the lease, the probe, Redis."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.redis = FakeRedis()
        self.requests: list[Any] = []
        self.pending: dict[str, Any] | None = None
        self.lease_acquired = True
        self.lease_attempts = 0
        self.result = RunResult(outcome=RunOutcome.SUCCESS, text="C'est noté.", attempts=1)
        self.run_seconds = 0.0
        self.cancelled = 0

        async def _redis() -> FakeRedis:
            return self.redis

        async def _pending(_conversation_id: str) -> dict[str, Any] | None:
            return self.pending

        @contextlib.asynccontextmanager
        async def _lease(
            _redis: Any, _conversation_id: str, *, run_id: str, stream_id: str
        ) -> AsyncIterator[bool]:
            self.lease_attempts += 1
            yield self.lease_acquired

        async def _stream(request: Any) -> RunResult:
            self.requests.append(request)
            try:
                await asyncio.sleep(self.run_seconds)
            except asyncio.CancelledError:
                self.cancelled += 1
                raise
            return self.result

        monkeypatch.setattr(bridge, "get_redis_cache", _redis)
        monkeypatch.setattr(bridge, "check_pending_hitl_uncached", _pending)
        monkeypatch.setattr(bridge, "active_run_lease", _lease)
        monkeypatch.setattr(bridge, "stream_instruction", _stream)
        monkeypatch.setattr(settings, "voice_delegation_lease_wait_seconds", 1, raising=False)
        monkeypatch.setattr(settings, "live_delegation_result_max_tokens", 600, raising=False)
        monkeypatch.setattr(bridge, "SUPERSEDE_POLL_SECONDS", 0.01)


@pytest.fixture
def rig(monkeypatch: pytest.MonkeyPatch) -> Rig:
    return Rig(monkeypatch)


async def test_an_empty_request_costs_nothing(rig: Rig) -> None:
    result = await delegate(_request(_session(), "   "), context=_context())
    assert result.outcome is DelegationOutcome.EMPTY
    assert result.text == bridge.bridge_lines()["empty_request"]
    assert rig.requests == []


async def test_the_answer_is_a_spoken_turn_of_the_person_stamped_with_the_session(
    rig: Rig,
) -> None:
    session = _session()
    result = await delegate(_request(session), context=_context())
    assert result.outcome is DelegationOutcome.ANSWERED
    assert result.text == "C'est noté."
    stream = rig.requests[0]
    assert stream.prompt == "Rappelle-moi la banque demain"
    assert stream.spoken_text == "rappelle moi la banque demain"
    assert stream.live_session_id == session.key
    assert stream.spoken_by_person is True
    assert stream.execution_mode == "react"
    assert stream.memory_enabled is True and stream.psyche_enabled is True
    # An ordinary chat turn: no out-of-turn origin, the graph mints the run id.
    assert stream.origin is None
    assert stream.run_id is None and stream.original_run_id is None
    assert stream.max_attempts == 1


async def test_the_answer_is_flattened_and_bounded_with_the_cut_stated(rig: Rig) -> None:
    rig.result = RunResult(
        outcome=RunOutcome.SUCCESS,
        text="<div class='lia-response'><p>Un <b>rappel</b> est posé.</p></div> " + "mot " * 900,
        attempts=1,
    )
    result = await delegate(_request(_session()), context=_context())
    assert result.text.startswith("Un rappel est posé.")
    assert result.text.endswith(bridge.bridge_lines()["result_cut"])
    assert "<" not in result.text


async def test_the_delivery_note_travels_beside_the_answer(rig: Rig) -> None:
    rig.result = RunResult(outcome=RunOutcome.SUCCESS, text="ok", attempts=1, register="warm")
    result = await delegate(_request(_session()), context=_context())
    assert result.note == bridge.tone_lines()["warm"]


async def test_an_unknown_register_hands_no_note(rig: Rig) -> None:
    rig.result = RunResult(outcome=RunOutcome.SUCCESS, text="ok", attempts=1, register="nope")
    result = await delegate(_request(_session()), context=_context())
    assert result.note is None


async def test_a_question_lia_asked_is_the_result(rig: Rig) -> None:
    rig.result = RunResult(
        outcome=RunOutcome.WAITING,
        text="",
        attempts=1,
        interrupt=TurnInterrupt(kind="draft_critique", question="Je l'envoie à Marie ?"),
    )
    result = await delegate(_request(_session()), context=_context())
    assert result.outcome is DelegationOutcome.QUESTION
    assert result.text == "Je l'envoie à Marie ?"


async def test_the_next_request_resumes_the_run_that_asked(rig: Rig) -> None:
    rig.pending = {"run_id": "run-asked", "action_requests": [{"type": "draft_critique"}]}
    await delegate(_request(_session(), "Oui, envoie"), context=_context())
    stream = rig.requests[0]
    assert stream.original_run_id == "run-asked"
    assert stream.run_id == "run-asked"


async def test_a_wait_past_the_bound_leaves_the_turn_running(rig: Rig) -> None:
    rig.run_seconds = 0.3
    result = await delegate(_request(_session(), wait_seconds=0.05), context=_context())
    assert result.outcome is DelegationOutcome.TIMED_OUT
    assert result.text == bridge.bridge_lines()["timed_out"]
    assert rig.cancelled == 0
    # The turn ends in the thread on its own.
    await asyncio.sleep(0.4)
    assert rig.cancelled == 0


async def test_the_newest_request_wins_and_the_old_caller_hears_it(rig: Rig) -> None:
    session = _session()
    rig.run_seconds = 1.0
    first = asyncio.create_task(
        delegate(_request(session, "Première demande", request_id="call-1"), context=_context())
    )
    await asyncio.sleep(0.05)
    second = asyncio.create_task(
        delegate(
            _request(session, "Première demande, pour lundi", request_id="call-2"),
            context=_context(),
        )
    )
    first_result = await first
    assert first_result.outcome is DelegationOutcome.SUPERSEDED
    assert first_result.text == bridge.bridge_lines()["superseded"]
    assert rig.cancelled == 1
    rig.run_seconds = 0.0
    second_result = await asyncio.wait_for(second, 3)
    assert second_result.outcome is DelegationOutcome.ANSWERED
    assert [r.prompt for r in rig.requests] == ["Première demande", "Première demande, pour lundi"]


async def test_a_turn_still_running_after_a_timeout_is_cancelled_by_the_next(rig: Rig) -> None:
    session = _session()
    rig.run_seconds = 1.0
    first = await delegate(
        _request(session, "A", request_id="call-1", wait_seconds=0.05), context=_context()
    )
    assert first.outcome is DelegationOutcome.TIMED_OUT
    rig.run_seconds = 0.0
    second = await asyncio.wait_for(
        delegate(_request(session, "B", request_id="call-2"), context=_context()), 3
    )
    assert second.outcome is DelegationOutcome.ANSWERED

    # The first turn's supervisor reads the marker at its next poll — after
    # the second answered (its turn ran in no time): bounded wait, not a race.
    async def _cancelled() -> None:
        while rig.cancelled < 1:
            await asyncio.sleep(0.01)

    await asyncio.wait_for(_cancelled(), 3)
    assert rig.cancelled == 1


async def test_a_request_replaced_while_it_waited_for_the_lease_starts_no_turn(rig: Rig) -> None:
    # Two vendor webhooks may land on two workers: the older one, still waiting
    # for the conversation's lease, must read the marker BEFORE it takes the
    # lease and starts a turn it would cancel 250 ms later — a router call and
    # a checkpoint paid for a request nobody wants any more.
    session = _session()
    rig.lease_acquired = False
    older = asyncio.create_task(
        delegate(_request(session, "A", request_id="call-1"), context=_context())
    )
    await asyncio.sleep(0.05)
    await rig.redis.set(bridge.newest_request_key(session.key), "call-2")
    rig.lease_acquired = True
    result = await asyncio.wait_for(older, 3)
    assert result.outcome is DelegationOutcome.SUPERSEDED
    assert rig.requests == []


async def test_a_busy_conversation_is_named_not_waited_for_ever(rig: Rig) -> None:
    rig.lease_acquired = False
    result = await delegate(_request(_session()), context=_context())
    assert result.outcome is DelegationOutcome.BUSY
    assert result.text == bridge.bridge_lines()["busy"]
    assert rig.requests == []
    assert rig.lease_attempts >= 2


async def test_a_spend_ceiling_is_told_to_the_voice(rig: Rig) -> None:
    rig.result = RunResult(outcome=RunOutcome.QUOTA_BLOCKED, text="", attempts=1, error="limit")
    result = await delegate(_request(_session()), context=_context())
    assert result.outcome is DelegationOutcome.QUOTA_BLOCKED
    assert result.text == bridge.bridge_lines()["quota_blocked"]


async def test_a_failed_turn_never_reaches_the_voice_as_an_exception(rig: Rig) -> None:
    rig.result = RunResult(outcome=RunOutcome.FAILED, text="", attempts=1, error="boom")
    result = await delegate(_request(_session()), context=_context())
    assert result.outcome is DelegationOutcome.FAILED
    assert result.text == bridge.bridge_lines()["failed"]


async def test_a_probe_that_fails_still_runs_the_turn_without_resumption(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _boom(_conversation_id: str) -> dict[str, Any] | None:
        raise RuntimeError("redis down")

    monkeypatch.setattr(bridge, "check_pending_hitl_uncached", _boom)
    result = await delegate(_request(_session()), context=_context())
    assert result.outcome is DelegationOutcome.ANSWERED
    assert rig.requests[0].original_run_id is None


async def test_the_newest_marker_is_a_runtime_key_with_a_ttl(rig: Rig) -> None:
    session = _session()
    await delegate(_request(session, request_id="call-9"), context=_context())
    key = bridge.newest_request_key(session.key)
    assert rig.redis.store[key] == "call-9"
    assert rig.redis.ttls[key] > 0
