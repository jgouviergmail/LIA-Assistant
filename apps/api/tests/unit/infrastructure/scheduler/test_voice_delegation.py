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
import uuid
from collections.abc import Awaitable, Callable

import pytest

import src.infrastructure.scheduler.voice_delegation as bridge
from src.core.config import settings
from src.domains.voice_sessions.mandate import bridge_lines, tone_lines
from src.domains.voice_sessions.session import VoiceSession
from src.infrastructure.scheduler.out_of_turn_run import (
    RunContext,
    RunOutcome,
    RunResult,
    StreamRequest,
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

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
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
    session: VoiceSession,
    text: str = "Rappelle-moi la banque demain",
    *,
    request_id: str = "call-1",
    wait_seconds: float = 5.0,
) -> DelegationRequest:
    return DelegationRequest(
        session=session,
        request_id=request_id,
        request=text,
        spoken_text="rappelle moi la banque demain",
        wait_seconds=wait_seconds,
    )


class Rig:
    """The admitted engine and Redis, with observable scheduling boundaries."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.redis = FakeRedis()
        self.requests: list[StreamRequest] = []
        self.admission_available = True
        self.admission_attempts = 0
        self.admission_refused = asyncio.Event()
        self.run_started = asyncio.Event()
        self.before_admission: Callable[[], Awaitable[None]] | None = None
        self.result = RunResult(outcome=RunOutcome.SUCCESS, text="C'est noté.", attempts=1)
        self.run_seconds = 0.0
        self.cancelled = 0

        async def _redis() -> FakeRedis:
            return self.redis

        async def _stream(
            request: StreamRequest,
            *,
            before_run: Callable[[], Awaitable[None]] | None = None,
        ) -> RunResult:
            self.admission_attempts += 1
            if not self.admission_available:
                self.admission_refused.set()
                return RunResult(outcome=RunOutcome.BUSY)
            if self.before_admission is not None:
                await self.before_admission()
            if before_run is not None:
                await before_run()
            self.requests.append(request)
            self.run_started.set()
            try:
                await asyncio.sleep(self.run_seconds)
            except asyncio.CancelledError:
                self.cancelled += 1
                raise
            return self.result

        monkeypatch.setattr(bridge, "get_redis_cache", _redis)
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
    assert result.text == bridge_lines()["empty_request"]
    assert rig.requests == []


@pytest.mark.parametrize("failure_at", ["connection", "marker", "supervision"])
@pytest.mark.parametrize("error_type", [ConnectionError, TimeoutError])
async def test_redis_failure_before_supervision_starts_no_turn_and_is_named(
    rig: Rig, monkeypatch: pytest.MonkeyPatch, failure_at: str, error_type: type[Exception]
) -> None:
    """A missing supersession marker cannot become an unguarded voice turn."""

    async def unavailable() -> FakeRedis:
        raise error_type("Disposable Redis unavailable")

    async def write_failed(key: str, value: str, *, ex: int) -> bool:
        raise error_type("Marker unavailable")

    async def read_failed(key: str) -> str | None:
        raise error_type("Marker unavailable")

    if failure_at == "connection":
        monkeypatch.setattr(bridge, "get_redis_cache", unavailable)
    elif failure_at == "marker":
        monkeypatch.setattr(rig.redis, "set", write_failed)
    else:
        monkeypatch.setattr(rig.redis, "get", read_failed)
    result = await delegate(_request(_session()), context=_context())

    assert result.outcome is DelegationOutcome.FAILED
    assert result.text == bridge_lines()["failed"]
    assert rig.requests == []
    assert rig.admission_attempts == 0


@pytest.mark.parametrize("error_type", [ConnectionError, TimeoutError])
async def test_a_failed_poll_joins_the_running_turn_before_reporting_failure(
    rig: Rig, monkeypatch: pytest.MonkeyPatch, error_type: type[Exception]
) -> None:
    """A supervisor's failed Redis read must not abandon its graph task."""
    started = asyncio.Event()
    closed = asyncio.Event()
    release = asyncio.Event()
    original_get = rig.redis.get

    async def read_marker(key: str) -> str | None:
        if started.is_set():
            raise error_type("Polling unavailable")
        return await original_get(key)

    async def stream(
        request: StreamRequest,
        *,
        before_run: Callable[[], Awaitable[None]] | None = None,
    ) -> RunResult:
        if before_run is not None:
            await before_run()
        started.set()
        try:
            await release.wait()
            return rig.result
        finally:
            closed.set()

    monkeypatch.setattr(rig.redis, "get", read_marker)
    monkeypatch.setattr(bridge, "stream_instruction", stream)
    try:
        result = await delegate(_request(_session()), context=_context())
        assert result.outcome is DelegationOutcome.FAILED
        assert result.text == bridge_lines()["failed"]
        assert started.is_set()
        assert closed.is_set(), "The failed supervisor returned with its graph still alive"
    finally:
        # A failing oracle must still join the test's own deliberately blocked work.
        release.set()
        await asyncio.wait_for(closed.wait(), 3)


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
    # The person is on the line: their wait is a chat latency (latency_sli).
    assert stream.person_waiting is True
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
    assert result.text.endswith(bridge_lines()["result_cut"])
    assert "<" not in result.text


async def test_the_delivery_note_travels_beside_the_answer(rig: Rig) -> None:
    rig.result = RunResult(outcome=RunOutcome.SUCCESS, text="ok", attempts=1, register="warm")
    result = await delegate(_request(_session()), context=_context())
    assert result.note == tone_lines()["warm"]


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


async def test_the_next_request_asks_the_admitted_engine_to_resolve_resumption(rig: Rig) -> None:
    await delegate(_request(_session(), "Oui, envoie"), context=_context())
    stream = rig.requests[0]
    assert stream.resume_pending is True
    assert stream.original_run_id is None and stream.run_id is None


async def test_a_wait_past_the_bound_leaves_the_turn_running(rig: Rig) -> None:
    rig.run_seconds = 0.3
    result = await delegate(_request(_session(), wait_seconds=0.05), context=_context())
    assert result.outcome is DelegationOutcome.TIMED_OUT
    assert result.text == bridge_lines()["timed_out"]
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
    await asyncio.wait_for(rig.run_started.wait(), 3)
    second = asyncio.create_task(
        delegate(
            _request(session, "Première demande, pour lundi", request_id="call-2"),
            context=_context(),
        )
    )
    first_result = await first
    assert first_result.outcome is DelegationOutcome.SUPERSEDED
    assert first_result.text == bridge_lines()["superseded"]
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


async def test_a_request_replaced_while_it_waited_for_admission_starts_no_turn(rig: Rig) -> None:
    # Two vendor webhooks may land on two workers: the older one, still waiting
    # for account admission, must read the marker BEFORE it starts a turn
    # it would cancel at its next poll — a router call and
    # a checkpoint paid for a request nobody wants any more.
    session = _session()
    rig.admission_available = False
    older = asyncio.create_task(
        delegate(_request(session, "A", request_id="call-1"), context=_context())
    )
    await asyncio.wait_for(rig.admission_refused.wait(), 3)
    await rig.redis.set(bridge.newest_request_key(session.key), "call-2")
    rig.admission_available = True
    result = await asyncio.wait_for(older, 3)
    assert result.outcome is DelegationOutcome.SUPERSEDED
    assert rig.requests == []


async def test_a_request_replaced_during_admission_starts_no_turn(rig: Rig) -> None:
    """A newer marker during SQL admission must win before the first model call."""
    session = _session()

    async def replace_during_admission() -> None:
        await rig.redis.set(bridge.newest_request_key(session.key), "call-2")

    rig.before_admission = replace_during_admission
    result = await delegate(_request(session, "A", request_id="call-1"), context=_context())

    assert result.outcome is DelegationOutcome.SUPERSEDED
    assert rig.admission_attempts == 1
    assert rig.requests == []


async def test_a_busy_conversation_is_named_not_waited_for_ever(rig: Rig) -> None:
    rig.admission_available = False
    result = await delegate(_request(_session()), context=_context())
    assert result.outcome is DelegationOutcome.BUSY
    assert result.text == bridge_lines()["busy"]
    assert rig.requests == []
    assert rig.admission_attempts >= 2


async def test_a_spend_ceiling_is_told_to_the_voice(rig: Rig) -> None:
    rig.result = RunResult(outcome=RunOutcome.QUOTA_BLOCKED, text="", attempts=1, error="limit")
    result = await delegate(_request(_session()), context=_context())
    assert result.outcome is DelegationOutcome.QUOTA_BLOCKED
    assert result.text == bridge_lines()["quota_blocked"]


async def test_a_failed_turn_never_reaches_the_voice_as_an_exception(rig: Rig) -> None:
    rig.result = RunResult(outcome=RunOutcome.FAILED, text="", attempts=1, error="boom")
    result = await delegate(_request(_session()), context=_context())
    assert result.outcome is DelegationOutcome.FAILED
    assert result.text == bridge_lines()["failed"]


async def test_an_engine_refusing_unreadable_state_is_a_failure(rig: Rig) -> None:
    rig.result = RunResult(outcome=RunOutcome.FAILED, error_code="CacheError")
    result = await delegate(_request(_session()), context=_context())
    assert result.outcome is DelegationOutcome.FAILED


async def test_the_newest_marker_is_a_runtime_key_with_a_ttl(rig: Rig) -> None:
    session = _session()
    await delegate(_request(session, request_id="call-9"), context=_context())
    key = bridge.newest_request_key(session.key)
    assert rig.redis.store[key] == "call-9"
    assert rig.redis.ttls[key] > 0
