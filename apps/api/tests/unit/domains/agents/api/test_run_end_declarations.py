"""Every driver of a run declares how it ended, from an explicit result (ADR-384).

The close writes that end; an end nobody declared is read as interrupted, so a
driver that forgets to declare a normal end holds every waiting message.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from importlib import import_module
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.conversation_execution import ExecutionKind, RunAdmission, RunEnd
from src.core.conversation_target import ConversationKind, ConversationRef
from src.core.run_authority import RunAuthority, current_run_authority, run_authority_scope
from src.domains.agents.api import background_runner
from src.domains.agents.api.run_output import RunEndStatus
from src.domains.agents.api.schemas import ChatStreamChunk
from src.infrastructure.scheduler import out_of_turn_run
from src.infrastructure.scheduler.out_of_turn_run import RunOutcome, run_end_of
from tests.fixtures.instruction_runtime import instruction_runtime

pytestmark = pytest.mark.unit


def _admission() -> RunAdmission:
    target = ConversationRef(uuid4(), uuid4(), ConversationKind.MAIN, 0, uuid4())
    return RunAdmission(
        uuid4(), target, ExecutionKind.GRAPH, "run", "stream", uuid4(), uuid4(), 1, False
    )


class _Output:
    def __init__(self) -> None:
        self.status: RunEndStatus | None = None

    async def publish(self, chunk: ChatStreamChunk) -> None:
        return None

    async def finish(self, status: RunEndStatus) -> None:
        self.status = status


async def _produce(
    stream: AsyncGenerator[ChatStreamChunk], monkeypatch: pytest.MonkeyPatch
) -> RunAuthority:
    monkeypatch.setattr(background_runner, "get_redis_cache", AsyncMock(return_value=object()))
    monkeypatch.setattr(background_runner, "is_cancel_requested", AsyncMock(return_value=False))
    admission = _admission()
    authority = RunAuthority(admission)
    with run_authority_scope(authority):
        await background_runner._produce(stream, admission, "session", _Output(), None)
    return authority


async def test_a_completed_answer_declares_a_normal_end(monkeypatch: pytest.MonkeyPatch) -> None:
    async def stream() -> AsyncGenerator[ChatStreamChunk]:
        yield ChatStreamChunk(type="token", content="Done.")
        yield ChatStreamChunk(type="done", content="")

    assert (await _produce(stream(), monkeypatch)).end == RunEnd.NORMAL


async def test_an_answer_that_published_an_error_is_interrupted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def stream() -> AsyncGenerator[ChatStreamChunk]:
        yield ChatStreamChunk(type="error", content="refused", metadata={"error_code": "x"})
        yield ChatStreamChunk(type="done", content="")

    assert (await _produce(stream(), monkeypatch)).end == RunEnd.INTERRUPTED


async def test_a_failing_stream_is_interrupted(monkeypatch: pytest.MonkeyPatch) -> None:
    async def stream() -> AsyncGenerator[ChatStreamChunk]:
        yield ChatStreamChunk(type="token", content="Half")
        raise RuntimeError("provider down")

    assert (await _produce(stream(), monkeypatch)).end == RunEnd.INTERRUPTED


async def test_a_stopped_answer_is_interrupted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(background_runner, "get_redis_cache", AsyncMock(return_value=object()))
    monkeypatch.setattr(background_runner, "is_cancel_requested", AsyncMock(return_value=False))
    started = asyncio.Event()

    async def stream() -> AsyncGenerator[ChatStreamChunk]:
        yield ChatStreamChunk(type="token", content="Half")
        started.set()
        await asyncio.Event().wait()
        yield ChatStreamChunk(type="done", content="")

    admission = _admission()
    authority = RunAuthority(admission)

    async def run() -> None:
        with run_authority_scope(authority):
            await background_runner._produce(stream(), admission, "session", _Output(), None)

    producer = asyncio.create_task(run())
    await asyncio.wait_for(started.wait(), timeout=5)
    producer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await producer
    assert authority.end == RunEnd.INTERRUPTED


@pytest.mark.parametrize(
    ("outcome", "end"),
    [
        (RunOutcome.SUCCESS, RunEnd.NORMAL),
        (RunOutcome.WAITING, RunEnd.NORMAL),
        (RunOutcome.FAILED, RunEnd.INTERRUPTED),
        (RunOutcome.QUOTA_BLOCKED, RunEnd.INTERRUPTED),
        (RunOutcome.BUSY, RunEnd.UNSTARTED),
        (RunOutcome.PENDING_QUESTION, RunEnd.UNSTARTED),
    ],
)
def test_an_out_of_turn_outcome_names_its_end(outcome: RunOutcome, end: RunEnd) -> None:
    assert run_end_of(outcome) == end


def test_every_out_of_turn_outcome_is_mapped() -> None:
    assert {outcome: run_end_of(outcome) for outcome in RunOutcome}.keys() == set(RunOutcome)


@pytest.mark.parametrize("outcome", [RunOutcome.SUCCESS, RunOutcome.FAILED])
async def test_an_admitted_out_of_turn_run_declares_its_settled_end(
    outcome: RunOutcome,
) -> None:
    owner = uuid4()
    seen: list[RunAuthority | None] = []

    async def settled(request: object) -> out_of_turn_run.RunResult:
        seen.append(current_run_authority())
        return out_of_turn_run.RunResult(outcome=outcome)

    request = out_of_turn_run.StreamRequest(
        user_id=owner,
        prompt="check",
        session_id="s",
        language="fr",
        timezone="Europe/Paris",
        display_name="Reader",
        display_mode="markdown",
        timeout_seconds=30,
        max_attempts=1,
        retry_delay_seconds=0,
    )
    with (
        instruction_runtime(owner),
        patch.object(out_of_turn_run, "_attempt_until_settled", settled),
    ):
        result = await out_of_turn_run._drive_admitted(request, None)
    assert result.outcome == outcome
    [authority] = seen
    assert authority is not None and authority.end == run_end_of(outcome)


async def test_a_channel_turn_declares_a_normal_end_when_its_stream_completes() -> None:
    port = import_module("src.infrastructure.channels.assistant_gateway")
    adapter = import_module("src.domains.agents.api.channel_gateway")
    owner = uuid4()
    seen: list[RunAuthority | None] = []

    async def response(**_kwargs: object) -> AsyncGenerator[ChatStreamChunk]:
        seen.append(current_run_authority())
        yield ChatStreamChunk(type="token", content="Bonjour")
        yield ChatStreamChunk(type="done", content="")

    request = port.ChannelAgentRequest(
        user_message="Bonjour",
        user_id=owner,
        session_id="channel-session",
        user_timezone="Europe/Paris",
        user_language="fr",
        user_memory_enabled=False,
        original_run_id=None,
        user_display_name="Reader",
        user_journals_enabled=False,
        user_psyche_enabled=False,
        hitl_decision=None,
    )
    with (
        instruction_runtime(owner),
        patch(
            "src.domains.agents.api.hitl_pending.check_pending_hitl_uncached",
            AsyncMock(return_value=None),
        ),
        patch("src.domains.agents.api.service.AgentService") as service,
    ):
        service.return_value.stream_chat_response = response
        chunks = [chunk async for chunk in adapter.build_channel_gateway().stream(request)]
    assert [chunk.type for chunk in chunks] == ["token", "done"]
    [authority] = seen
    assert authority is not None and authority.end == RunEnd.NORMAL


async def test_a_channel_turn_that_relayed_an_error_is_interrupted() -> None:
    port = import_module("src.infrastructure.channels.assistant_gateway")
    adapter = import_module("src.domains.agents.api.channel_gateway")
    owner = uuid4()
    seen: list[RunAuthority | None] = []

    async def response(**_kwargs: object) -> AsyncGenerator[ChatStreamChunk]:
        seen.append(current_run_authority())
        yield ChatStreamChunk(type="error", content="refused", metadata={"error_code": "x"})
        yield ChatStreamChunk(type="done", content="")

    request = port.ChannelAgentRequest(
        user_message="Bonjour",
        user_id=owner,
        session_id="channel-session",
        user_timezone="Europe/Paris",
        user_language="fr",
        user_memory_enabled=False,
        original_run_id=None,
        user_display_name="Reader",
        user_journals_enabled=False,
        user_psyche_enabled=False,
        hitl_decision=None,
    )
    with (
        instruction_runtime(owner),
        patch(
            "src.domains.agents.api.hitl_pending.check_pending_hitl_uncached",
            AsyncMock(return_value=None),
        ),
        patch("src.domains.agents.api.service.AgentService") as service,
    ):
        service.return_value.stream_chat_response = response
        [_ async for _ in adapter.build_channel_gateway().stream(request)]
    [authority] = seen
    assert authority is not None and authority.end == RunEnd.INTERRUPTED
