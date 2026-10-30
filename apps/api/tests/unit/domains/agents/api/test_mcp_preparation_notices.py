"""A person waiting for their personal servers is told which one is slow (spec 2026-10-21 §5.6, M4).

The turn prepares the servers before the graph (§5.3); a cold or slow one can
hold the answer back for up to the ceiling. While it waits, the turn streams
notices — never on a warm turn, never to a channel, a routine, the phone or the
live voice, never into the state, the archive or the first-token timing:

- one generic ``mcp_preparation`` progress step (``execution.steps.*``) as soon
  as one server goes to the network;
- ``chat.mcp_preparation.slow`` for a server still discovering past the notice
  delay, then its terminal phase (``ready`` / ``failed`` / ``deferred``).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest

from src.core.context import UserMCPToolsContext, user_mcp_tools_ctx
from src.domains.agents.api.run_origin import RunOrigin, out_of_turn_origin_ctx, plain_surface_ctx
from src.domains.agents.api.schemas import ChatStreamChunk, MCPPreparationNotice
from src.domains.agents.api.turn_preparation import (
    PreparedUserMCP,
    iter_mcp_preparation,
    notices_reach_the_person,
)
from src.domains.agents.services.streaming.journey_timing import JourneyTiming
from src.domains.agents.services.streaming.latency_sli import awaited_by_a_person
from src.infrastructure.mcp.user_preparation import PreparationEvent

pytestmark = pytest.mark.unit

NOTES, FILES = uuid4(), uuid4()


def _event(server: UUID, phase: str, elapsed: float = 0.0) -> PreparationEvent:
    name = "Notes" if server == NOTES else "Files"
    return PreparationEvent(server, name, phase, elapsed)  # type: ignore[arg-type]


async def _run(
    events: list[PreparationEvent], *, interactive: bool = True
) -> tuple[list[ChatStreamChunk], list[PreparedUserMCP], list[bool]]:
    asked: list[bool] = []
    ctx = UserMCPToolsContext()

    async def prepare(user_id: UUID, *, on_event: Any = None) -> UserMCPToolsContext:
        asked.append(on_event is not None)
        for event in events:
            if on_event is not None:
                on_event(event)
        return ctx

    chunks: list[ChatStreamChunk] = []
    prepared: list[PreparedUserMCP] = []
    with patch("src.infrastructure.mcp.user_context.prepare_user_mcp_context", prepare):
        async for item in iter_mcp_preparation(uuid4(), run_id="run-1", interactive=interactive):
            (prepared if isinstance(item, PreparedUserMCP) else chunks).append(item)
    return chunks, prepared, asked


def _notices(chunks: list[ChatStreamChunk]) -> list[tuple[str, str | None, str]]:
    notices = [MCPPreparationNotice.model_validate(chunk.metadata) for chunk in chunks]
    return [(notice.i18n_key, notice.server_name, notice.phase) for notice in notices]


async def test_warm_turn_emits_no_notice() -> None:
    chunks, prepared, _ = await _run(
        [_event(NOTES, "queued"), _event(NOTES, "embeddings"), _event(NOTES, "ready")]
    )

    assert chunks == []
    assert len(prepared) == 1


async def test_slow_notice_emitted_at_threshold_before_graph() -> None:
    chunks, prepared, _ = await _run(
        [
            _event(NOTES, "queued"),
            _event(NOTES, "discovering", 0.01),
            _event(NOTES, "slow", 10.0),
            _event(NOTES, "ready", 12.5),
        ]
    )

    assert _notices(chunks) == [
        ("mcp_preparation", None, "discovering"),
        ("chat.mcp_preparation.slow", "Notes", "slow"),
        ("chat.mcp_preparation.ready", "Notes", "ready"),
    ]
    assert all(chunk.type == "execution_step" for chunk in chunks)
    slow = MCPPreparationNotice.model_validate(chunks[1].metadata)
    assert slow.elapsed_ms == 10_000 and slow.server_key == str(NOTES)
    assert len(prepared) == 1  # the context comes after every notice, before the graph


async def test_terminal_phase_follows_slow() -> None:
    chunks, _, _ = await _run(
        [
            _event(NOTES, "discovering"),
            _event(FILES, "discovering"),
            _event(NOTES, "slow", 10.0),
            _event(FILES, "ready", 1.0),  # never slow: no notice of its own
            _event(NOTES, "timed_out", 15.0),
        ]
    )

    assert _notices(chunks) == [
        ("mcp_preparation", None, "discovering"),
        ("chat.mcp_preparation.slow", "Notes", "slow"),
        ("chat.mcp_preparation.failed", "Notes", "timed_out"),
    ]


async def test_a_server_left_at_the_ceiling_says_so() -> None:
    chunks, _, _ = await _run(
        [_event(NOTES, "discovering"), _event(NOTES, "slow", 10.0), _event(NOTES, "deferred", 20.0)]
    )

    assert _notices(chunks)[-1] == ("chat.mcp_preparation.deferred", "Notes", "deferred")


async def test_not_interactive_asks_for_no_event() -> None:
    chunks, prepared, asked = await _run([_event(NOTES, "discovering")], interactive=False)

    assert chunks == [] and len(prepared) == 1 and asked == [False]


@contextmanager
def _surface(**kind: Any) -> Iterator[None]:
    tokens: list[Any] = []
    if kind.get("channel"):
        tokens.append((plain_surface_ctx, plain_surface_ctx.set(True)))
    if kind.get("routine"):
        tokens.append(
            (
                out_of_turn_origin_ctx,
                out_of_turn_origin_ctx.set(RunOrigin(kind="routine", ticket_id="r", run_id="r")),
            )
        )
    try:
        with awaited_by_a_person(not kind.get("unattended", False)):
            yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


@pytest.mark.parametrize(
    ("kind", "live_session_id", "expected"),
    [
        ({}, None, True),
        ({"channel": True}, None, False),
        ({"routine": True}, None, False),
        ({"unattended": True}, None, False),
        ({}, "live-1", False),
    ],
    ids=["web chat", "channel", "routine or phone relay", "nobody waits", "live voice"],
)
def test_no_notice_on_channel_routine_phone_or_voice(
    kind: dict[str, Any], live_session_id: str | None, expected: bool
) -> None:
    with _surface(**kind):
        assert notices_reach_the_person(live_session_id) is expected


async def test_notices_never_archived_nor_in_state() -> None:
    from tests.agents.test_agent_service_stream_characterization import Harness, _router, _token

    harness = Harness(script=[_router("conversation"), _token("Bonjour")])
    harness.mcp_events = [_event(NOTES, "discovering"), _event(NOTES, "slow", 10.0)]
    with pytest.MonkeyPatch.context() as mp:
        chunks = await harness.run(mp)

    notices = [chunk for chunk in chunks if chunk.metadata.get("step_type") == "mcp_preparation"]
    assert [notice.metadata["i18n_key"] for notice in notices] == [
        "mcp_preparation",
        "chat.mcp_preparation.slow",
    ]
    assert chunks.index(notices[-1]) < next(
        index for index, chunk in enumerate(chunks) if chunk.type == "router_decision"
    )
    archived = repr(harness.conv_service.archived)
    assert "mcp_preparation" not in archived and "preparing_applications" not in archived
    assert "mcp_preparation" not in repr(harness.graph_stream_kwargs)


def test_notice_is_not_first_token() -> None:
    timing = JourneyTiming()
    notice = MCPPreparationNotice(
        i18n_key="chat.mcp_preparation.slow",
        server_key=str(NOTES),
        server_name="Notes",
        phase="slow",
        elapsed_ms=10_000,
    )
    timing.observe("execution_step", "", notice.model_dump())

    assert timing.first_token_ms is None and timing.first_useful_ms is None


def test_the_installed_context_is_the_prepared_one() -> None:
    ctx = UserMCPToolsContext()
    token = PreparedUserMCP(ctx).install()
    try:
        assert user_mcp_tools_ctx.get() is ctx
    finally:
        assert token is not None
        user_mcp_tools_ctx.reset(token)
    assert PreparedUserMCP(None).install() is None


async def test_the_turn_streams_the_notices_then_installs_the_context() -> None:
    from src.domains.agents.api.turn_preparation import MCPPreparation

    ctx = UserMCPToolsContext()

    async def prepare(user_id: UUID, *, on_event: Any = None) -> UserMCPToolsContext:
        on_event(_event(NOTES, "discovering"))
        return ctx

    with patch("src.infrastructure.mcp.user_context.prepare_user_mcp_context", prepare):
        preparation = MCPPreparation(uuid4(), run_id="run-1", live_session_id=None)
        assert preparation.install() is None  # nothing prepared yet
        notices = [chunk async for chunk in preparation.notices()]
        assert user_mcp_tools_ctx.get() is None  # streamed before anything is installed
        token = preparation.install()
    try:
        assert len(notices) == 1 and user_mcp_tools_ctx.get() is ctx
    finally:
        assert token is not None
        user_mcp_tools_ctx.reset(token)


async def test_leaving_early_stops_the_wait_and_leaves_no_task() -> None:
    """The person went away: the turn stops waiting, and nothing it started dangles."""
    import asyncio
    from contextlib import suppress

    gate = asyncio.Event()

    async def prepare(user_id: UUID, *, on_event: Any = None) -> None:
        await gate.wait()

    async def drain() -> None:
        async for _item in iter_mcp_preparation(uuid4(), run_id="run-1", interactive=True):
            pass

    with patch("src.infrastructure.mcp.user_context.prepare_user_mcp_context", prepare):
        consumer = asyncio.create_task(drain())
        await asyncio.sleep(0.01)
        consumer.cancel()
        with suppress(asyncio.CancelledError):
            await consumer
    for _ in range(3):
        await asyncio.sleep(0)

    current = asyncio.current_task()
    assert [task for task in asyncio.all_tasks() if task is not current and not task.done()] == []
