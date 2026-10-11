"""An injected gateway preserves channel streaming context and rejects an unbound runner."""

from importlib import import_module
from unittest.mock import patch
from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit


def test_channel_cannot_fall_back_to_an_uninitialized_assistant() -> None:
    port = import_module("src.infrastructure.channels.assistant_gateway")
    previous = port.configure_channel_gateway(None)
    try:
        with pytest.raises(RuntimeError, match="not initialized"):
            port.get_channel_gateway()
    finally:
        port.configure_channel_gateway(previous)


async def test_real_adapter_forwards_consents_and_resets_plain_surface_on_cancellation() -> None:
    port = import_module("src.infrastructure.channels.assistant_gateway")
    adapter = import_module("src.domains.agents.api.channel_gateway")
    from src.domains.agents.api.run_origin import plain_surface_ctx
    from src.domains.agents.api.schemas import ChatStreamChunk

    actor_id = uuid4()
    request = port.ChannelAgentRequest(
        user_message="Bonjour",
        user_id=actor_id,
        session_id="channel-session",
        user_timezone="Europe/Paris",
        user_language="fr",
        user_memory_enabled=False,
        original_run_id="original",
        user_display_name="Reader",
        user_journals_enabled=True,
        user_psyche_enabled=False,
        hitl_decision={"decision": "approve"},
    )
    seen = []
    closed = []

    async def response(**kwargs: object):
        seen.append(kwargs)
        assert plain_surface_ctx.get() is True
        try:
            yield ChatStreamChunk(type="token", content="Bonjour")
        finally:
            closed.append(plain_surface_ctx.get())

    with patch("src.domains.agents.api.service.AgentService") as service:
        service.return_value.stream_chat_response = response
        stream = adapter.build_channel_gateway().stream(request)
        assert (await anext(stream)).content == "Bonjour"
        await stream.aclose()
    assert plain_surface_ctx.get() is False
    assert closed == [True]
    assert len(seen) == 1
    assert seen[0]["user_id"] == actor_id
    assert seen[0]["user_memory_enabled"] is False
    assert seen[0]["user_journals_enabled"] is True
    assert seen[0]["user_psyche_enabled"] is False
    assert seen[0]["original_run_id"] == "original"
    assert seen[0]["hitl_decision"] == {"decision": "approve"}
