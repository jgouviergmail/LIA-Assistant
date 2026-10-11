"""Prompts and continuity storage retain their contracts without reverse agent imports."""

from importlib import import_module
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from src.core.prompt_store import read_prompt_file
from src.domains.agents.prompts import load_prompt

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "name",
    [
        "heartbeat_decision_user_prompt",
        "heartbeat_verified_facts_prompt",
        "heartbeat_decision_prompt",
        "heartbeat_message_prompt",
        "heartbeat_wake_fresh_prompt",
    ],
)
def test_shared_reader_returns_the_existing_prompt_bytes(name: str) -> None:
    assert read_prompt_file(name) == load_prompt(name)


async def test_continuity_writer_is_injected_and_keeps_the_owner_payload() -> None:
    sink = import_module("src.infrastructure.proactive.context_sink")
    writer = AsyncMock()
    previous = sink.configure_proactive_context_writer(writer)
    actor_id = uuid4()
    value = {"content": "summary", "sources": ["OPEN_LOOPS"], "sent_at": "2026-10-07T00:00:00Z"}
    try:
        await sink.write_heartbeat_context(actor_id, value)
        writer.assert_awaited_once_with(actor_id, value)
    finally:
        sink.configure_proactive_context_writer(previous)


async def test_failed_restart_cannot_write_to_the_previous_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.domains.agents import context
    from src.infrastructure.startup.agents import init_agent_registry

    sink = import_module("src.infrastructure.proactive.context_sink")
    gateway = import_module("src.infrastructure.channels.assistant_gateway")
    old_writer = AsyncMock()
    previous = sink.configure_proactive_context_writer(old_writer)
    previous_gateway = gateway.configure_channel_gateway(Mock())
    monkeypatch.setattr(
        context, "get_tool_context_store", AsyncMock(side_effect=RuntimeError("store unavailable"))
    )
    try:
        assert await init_agent_registry(None, Mock()) is None
        with pytest.raises(RuntimeError, match="not initialized"):
            await sink.write_heartbeat_context(uuid4(), {"content": "new run"})
        old_writer.assert_not_awaited()
        with pytest.raises(RuntimeError, match="not initialized"):
            gateway.get_channel_gateway()
    finally:
        sink.configure_proactive_context_writer(previous)
        gateway.configure_channel_gateway(previous_gateway)
