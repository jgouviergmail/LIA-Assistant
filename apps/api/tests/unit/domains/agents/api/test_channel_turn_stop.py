"""A channel turn can be stopped like the chat's, and says it was (Telegram lot 33).

A Telegram turn was reserved NOT stoppable: neither the chat's Stop nor any
Telegram gesture could end it, and a person who wrote « stop » saw it kept as
their next message. The turn is now reserved stoppable, watches the stop
signal the chat's Stop writes (``request_cancel``), ends INTERRUPTED (ADR-384:
what waited is held) and says it was stopped — never as a failure.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from importlib import import_module
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from src.core.conversation_execution import RunAdmission, RunEnd
from src.core.conversation_target import ConversationRef
from src.core.field_names import FIELD_ERROR_CODE
from src.core.run_authority import RunAuthority, current_run_authority
from src.core.stream_codes import RUN_STOPPED_ERROR_CODE
from src.domains.agents.api.schemas import ChatStreamChunk
from tests.fixtures.instruction_runtime import instruction_runtime

pytestmark = pytest.mark.unit

_ADAPTER = "src.domains.agents.api.channel_gateway"
#: How long a step may take before the test fails rather than hangs.
_BOUND_SECONDS = 5


def _request(owner: UUID) -> Any:
    port = import_module("src.infrastructure.channels.assistant_gateway")
    return port.ChannelAgentRequest(
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
        user_execution_mode="pipeline",
        hitl_decision=None,
        position=None,
        attachment_ids=(),
    )


class _Reservations:
    """The admission's reservation, recorded, then the fixture's own fake."""

    def __init__(self, delegate: Any) -> None:
        self.delegate = delegate
        self.cancellable: list[bool] = []

    def __call__(self, owner_id: UUID, **kwargs: Any) -> Any:
        self.cancellable.append(kwargs.pop("cancellable", False))
        return self.delegate(owner_id, **kwargs)


@asynccontextmanager
async def _channel_runtime(owner: UUID) -> AsyncIterator[tuple[_Reservations, AsyncMock]]:
    module = import_module("src.domains.agents.api.internal_admission")
    with instruction_runtime(owner):
        reservations = _Reservations(module.execution_for_turn)
        forget = AsyncMock(return_value=True)
        with (
            patch.object(module, "execution_for_turn", reservations),
            patch(
                "src.infrastructure.cache.redis.get_redis_cache", AsyncMock(return_value=object())
            ),
            patch(f"{_ADAPTER}.forget_question_of_run", forget),
            patch(f"{_ADAPTER}.clear_cancel", AsyncMock()),
            patch(f"{_ADAPTER}.settings.background_runs_cancel_poll_seconds", 0.01),
        ):
            yield reservations, forget


async def test_a_channel_turn_is_reserved_stoppable() -> None:
    owner = uuid4()

    async def response(**_kwargs: object) -> AsyncGenerator[ChatStreamChunk]:
        yield ChatStreamChunk(type="done", content="")

    async with _channel_runtime(owner) as (reservations, _forget):
        with (
            patch(f"{_ADAPTER}.is_cancel_requested", AsyncMock(return_value=False)),
            patch("src.domains.agents.api.service.AgentService") as service,
        ):
            service.return_value.stream_chat_response = response
            adapter = import_module(_ADAPTER)
            [_ async for _ in adapter.build_channel_gateway().stream(_request(owner))]

    assert reservations.cancellable == [True]


async def test_a_requested_stop_ends_the_turn_said_as_stopped() -> None:
    owner = uuid4()
    seen: list[RunAuthority | None] = []
    closed: list[bool] = []

    async def response(**_kwargs: object) -> AsyncGenerator[ChatStreamChunk]:
        seen.append(current_run_authority())
        try:
            yield ChatStreamChunk(type="token", content="Je cherche")
            await asyncio.Event().wait()  # a model that would never answer
            yield ChatStreamChunk(type="token", content="jamais")
        finally:
            closed.append(True)

    polls = iter([False, True])
    async with _channel_runtime(owner) as (_reservations, forget):
        with (
            patch(
                f"{_ADAPTER}.is_cancel_requested",
                AsyncMock(side_effect=lambda *_a: next(polls, True)),
            ),
            patch("src.domains.agents.api.service.AgentService") as service,
        ):
            service.return_value.stream_chat_response = response
            adapter = import_module(_ADAPTER)
            # Bounded: a stop nobody honours fails the test instead of hanging it.
            async with asyncio.timeout(_BOUND_SECONDS):
                chunks = [
                    chunk async for chunk in adapter.build_channel_gateway().stream(_request(owner))
                ]
            consumer = asyncio.current_task()
            assert consumer is not None and consumer.cancelling() == 0

    assert [chunk.type for chunk in chunks] == ["token", "error"]
    assert chunks[1].metadata == {FIELD_ERROR_CODE: RUN_STOPPED_ERROR_CODE}
    assert closed == [True]
    [authority] = seen
    assert authority is not None and authority.end == RunEnd.INTERRUPTED
    # A question the stopped run may have saved is not left to read the
    # person's next message as its answer.
    forget.assert_awaited_once()
    admission: RunAdmission = forget.await_args.args[0]
    assert isinstance(admission.target, ConversationRef)
    assert admission.target.owner_id == owner


async def test_a_cancellation_that_is_no_stop_is_never_swallowed() -> None:
    owner = uuid4()
    started = asyncio.Event()

    async def response(**_kwargs: object) -> AsyncGenerator[ChatStreamChunk]:
        started.set()
        await asyncio.Event().wait()
        yield ChatStreamChunk(type="done", content="")

    async with _channel_runtime(owner) as (_reservations, forget):
        with (
            patch(f"{_ADAPTER}.is_cancel_requested", AsyncMock(return_value=False)),
            patch("src.domains.agents.api.service.AgentService") as service,
        ):
            service.return_value.stream_chat_response = response
            adapter = import_module(_ADAPTER)

            async def consume() -> None:
                [_ async for _ in adapter.build_channel_gateway().stream(_request(owner))]

            task = asyncio.create_task(consume())
            async with asyncio.timeout(_BOUND_SECONDS):
                await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                async with asyncio.timeout(_BOUND_SECONDS):
                    await task

    forget.assert_not_awaited()


async def test_a_turn_that_ended_leaves_no_watch_behind() -> None:
    owner = uuid4()
    polls = AsyncMock(return_value=False)

    async def response(**_kwargs: object) -> AsyncGenerator[ChatStreamChunk]:
        yield ChatStreamChunk(type="token", content="Bonjour")

    async with _channel_runtime(owner):
        with (
            patch(f"{_ADAPTER}.is_cancel_requested", polls),
            patch("src.domains.agents.api.service.AgentService") as service,
        ):
            service.return_value.stream_chat_response = response
            adapter = import_module(_ADAPTER)
            [_ async for _ in adapter.build_channel_gateway().stream(_request(owner))]
            asked = polls.await_count
            await asyncio.sleep(0.05)

    assert polls.await_count == asked
