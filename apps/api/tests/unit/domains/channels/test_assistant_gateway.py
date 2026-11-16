"""An injected gateway preserves channel streaming context and rejects an unbound runner."""

from importlib import import_module
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from tests.fixtures.instruction_runtime import instruction_runtime

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
        user_execution_mode="pipeline",
        hitl_decision={"decision": "approve"},
        position=None,
        attachment_ids=(),
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

    with (
        instruction_runtime(actor_id),
        patch(
            "src.domains.agents.api.hitl_pending.check_pending_hitl_uncached",
            AsyncMock(
                return_value={"run_id": "original", "action_requests": [{"type": "clarification"}]}
            ),
        ),
        patch("src.domains.agents.api.service.AgentService") as service,
    ):
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
    assert seen[0]["browser_context"] is None
    assert seen[0]["attachment_ids"] is None


@pytest.mark.parametrize(
    ("accuracy_m", "accuracy"), [(12.5, 12.5), (None, None)], ids=["measured", "unmeasured"]
)
async def test_a_shared_position_is_the_turn_s_consented_geolocation(
    accuracy_m: float | None, accuracy: float | None
) -> None:
    """Telegram lot 8: « near me » reads the pin the person just shared, as the
    chat's tools read the browser's position — and remember it only under the
    person's own opt-in, the same door (``capture_location_fire_and_forget``)."""
    port = import_module("src.infrastructure.channels.assistant_gateway")
    adapter = import_module("src.domains.agents.api.channel_gateway")
    from src.domains.agents.api.schemas import ChatStreamChunk

    actor_id = uuid4()
    request = port.ChannelAgentRequest(
        user_message="📍",
        user_id=actor_id,
        session_id="channel-session",
        user_timezone="Europe/Paris",
        user_language="fr",
        user_memory_enabled=True,
        original_run_id=None,
        user_display_name=None,
        user_journals_enabled=False,
        user_psyche_enabled=False,
        user_execution_mode="pipeline",
        hitl_decision=None,
        position=port.GeoPoint(48.85661, 2.35222, accuracy_m=accuracy_m),
        attachment_ids=(),
    )
    seen = []

    async def response(**kwargs: object):
        seen.append(kwargs)
        yield ChatStreamChunk(type="token", content="ok")

    with (
        instruction_runtime(actor_id),
        patch("src.domains.agents.api.service.AgentService") as service,
    ):
        service.return_value.stream_chat_response = response
        stream = adapter.build_channel_gateway().stream(request)
        assert (await anext(stream)).content == "ok"
        await stream.aclose()
    geolocation = seen[0]["browser_context"].geolocation
    assert (geolocation.lat, geolocation.lon, geolocation.accuracy) == (48.85661, 2.35222, accuracy)


async def test_files_received_on_a_channel_are_the_turn_s_attachments() -> None:
    """Telegram lot 11: the turn reads them as the chat's message reads its uploads."""
    port = import_module("src.infrastructure.channels.assistant_gateway")
    adapter = import_module("src.domains.agents.api.channel_gateway")
    from src.domains.agents.api.schemas import ChatStreamChunk

    actor_id, first, second = uuid4(), uuid4(), uuid4()
    request = port.ChannelAgentRequest(
        user_message="📎 photo.jpg",
        user_id=actor_id,
        session_id="channel-session",
        user_timezone="Europe/Paris",
        user_language="fr",
        user_memory_enabled=True,
        original_run_id=None,
        user_display_name=None,
        user_journals_enabled=False,
        user_psyche_enabled=False,
        user_execution_mode="pipeline",
        hitl_decision=None,
        position=None,
        attachment_ids=(first, second),
    )
    seen = []

    async def response(**kwargs: object):
        seen.append(kwargs)
        yield ChatStreamChunk(type="token", content="ok")

    with (
        instruction_runtime(actor_id),
        patch("src.domains.agents.api.service.AgentService") as service,
    ):
        service.return_value.stream_chat_response = response
        stream = adapter.build_channel_gateway().stream(request)
        assert (await anext(stream)).content == "ok"
        await stream.aclose()
    assert seen[0]["attachment_ids"] == [first, second]


# --- An answer heard (lot 25) ------------------------------------------------------


@pytest.fixture
def readout(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    from types import SimpleNamespace

    synthesize = AsyncMock(return_value=SimpleNamespace(audio=b"ID3mp3", cut=False, cost_eur=0.0))
    monkeypatch.setattr("src.domains.voice.text_readout.synthesize_user_text", synthesize)
    return synthesize


async def test_an_answer_is_heard_as_its_words_capped_like_the_chat_s_voice(
    readout: AsyncMock,
) -> None:
    """Read like the chat's voice comments (its sentence cap), under a run of its own."""
    from src.core.config import settings
    from src.core.constants import CHANNEL_VOICE_REPLY_MAX_CHARS, CHANNEL_VOICE_REPLY_RUN_PREFIX

    adapter = import_module("src.domains.agents.api.channel_gateway")
    owner = uuid4()
    answer = "## The weather\n\n**Sunny** in [Lyon](https://x.example). " + "More. " * 2000

    audio = await adapter.build_channel_gateway().speak(owner, "it", answer)

    assert audio == b"ID3mp3"
    kwargs = readout.await_args.kwargs
    assert (kwargs["user_id"], kwargs["user_language"]) == (owner, "it")
    assert kwargs["text"].startswith("The weather") and "**" not in kwargs["text"]
    assert "https://" not in kwargs["text"]
    assert len(kwargs["text"]) <= CHANNEL_VOICE_REPLY_MAX_CHARS
    assert kwargs["max_sentences"] == settings.voice_chat_mode_max_sentences
    assert kwargs["run_prefix"] == CHANNEL_VOICE_REPLY_RUN_PREFIX


async def test_an_answer_a_ceiling_refuses_is_not_heard(readout: AsyncMock) -> None:
    """Both ceilings are asked before a paid voice speaks (ADR-272): a refusal is no failure."""
    from src.core._exceptions_base import BaseAPIException

    readout.side_effect = BaseAPIException(status_code=429, detail="usage limit")
    adapter = import_module("src.domains.agents.api.channel_gateway")

    assert await adapter.build_channel_gateway().speak(uuid4(), "fr", "Bonjour.") is None


async def test_an_answer_with_no_words_is_not_synthesised(readout: AsyncMock) -> None:
    adapter = import_module("src.domains.agents.api.channel_gateway")

    assert await adapter.build_channel_gateway().speak(uuid4(), "fr", "  \n ") is None
    readout.assert_not_awaited()
