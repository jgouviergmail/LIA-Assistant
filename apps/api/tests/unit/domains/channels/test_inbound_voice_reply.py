"""A voice note is answered aloud too (Telegram lot 25).

The person spoke and LIA wrote back. With voice comments on — the chat's own
switch — the answer to a voice note also leaves as a voice message: its words
(never its cards), read like the chat's voice, after the text. A question, a
typed message, or voice comments off stay written; a voice that cannot be made
never undoes the answer already sent.

Through the real gateway, the engine and the synthesis substituted.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.channels.abstractions import ChannelInboundMessage
from src.domains.channels.inbound_handler import InboundMessageHandler
from src.domains.channels.models import ChannelType
from tests.fixtures.instruction_runtime import instruction_runtime

pytestmark = pytest.mark.unit

#: The person's language — never the instance's, so nothing passes by falling back.
_PERSON = next(code for code in ("it", "es") if code != settings.default_language)
_CARD = '<div class="lia-response-wrapper" data-card-version="2"><p>12 degrees</p></div>'


def _voice_note() -> ChannelInboundMessage:
    return ChannelInboundMessage(
        channel_type=ChannelType.TELEGRAM,
        channel_user_id="12345",
        voice_file_id="voice-1",
        voice_duration_seconds=3,
        message_id="5",
        raw_data={},
    )


def _typed() -> ChannelInboundMessage:
    return ChannelInboundMessage(
        channel_type=ChannelType.TELEGRAM, channel_user_id="12345", text="weather?", raw_data={}
    )


@pytest.fixture
def synthesis() -> Iterator[AsyncMock]:
    synthesize = AsyncMock(return_value=SimpleNamespace(audio=b"ID3mp3", cut=False, cost_eur=0.0))
    with (
        patch("src.domains.voice.text_readout.synthesize_user_text", synthesize),
        patch("src.infrastructure.channels.telegram.bot.get_bot", return_value=MagicMock()),
        patch(
            "src.infrastructure.channels.telegram.voice.transcribe_voice_message",
            AsyncMock(return_value="what is the weather"),
        ),
    ):
        yield synthesize


def _sender() -> AsyncMock:
    order: list[str] = []

    async def message(_chat: str, outbound: Any) -> str:
        order.append("text")
        return "1"

    async def voice(_chat: str, _audio: bytes) -> bool:
        order.append("voice")
        return True

    sender = AsyncMock(
        send_message=AsyncMock(side_effect=message),
        send_voice=AsyncMock(side_effect=voice),
        send_typing_indicator=AsyncMock(),
    )
    sender.order = order
    return sender


async def _turn(
    message: ChannelInboundMessage,
    sender: AsyncMock,
    *chunks: ChatStreamChunk,
    voice_enabled: bool = True,
    pending_hitl: dict[str, object] | None = None,
) -> None:
    async def response(**_engine: Any) -> AsyncIterator[ChatStreamChunk]:
        for chunk in chunks or (ChatStreamChunk(type="token", content="Sunny today."),):
            yield chunk

    owner = uuid4()
    with (
        instruction_runtime(owner),
        patch(
            "src.domains.agents.api.hitl_pending.check_pending_hitl_uncached",
            AsyncMock(return_value=None),
        ),
        patch("src.domains.agents.api.service.AgentService") as service,
    ):
        service.return_value.stream_chat_response = MagicMock(side_effect=response)
        await InboundMessageHandler(sender=sender).handle(
            message=message,
            user_id=owner,
            user_language=_PERSON,
            user_timezone="Europe/Rome",
            user_memory_enabled=True,
            user_journals_enabled=False,
            user_psyche_enabled=False,
            user_voice_enabled=voice_enabled,
            user_execution_mode="pipeline",
            conversation_id="conv-1",
            pending_hitl=pending_hitl,
        )


async def test_a_voice_note_is_answered_aloud_after_the_text(synthesis: AsyncMock) -> None:
    sender = _sender()
    answer = ChatStreamChunk(type="content_replacement", content=f"Sunny today.\n\n{_CARD}")

    await _turn(_voice_note(), sender, answer)

    assert sender.order == ["text", "voice"]
    sender.send_voice.assert_awaited_once_with("12345", b"ID3mp3")
    spoken = synthesis.await_args.kwargs["text"]
    assert spoken == "Sunny today." and "12 degrees" not in spoken
    assert synthesis.await_args.kwargs["user_language"] == _PERSON


@pytest.mark.parametrize(
    ("message", "voice_enabled"),
    [(_voice_note, False), (_typed, True)],
    ids=["voice_comments_off", "typed_message"],
)
async def test_what_was_not_said_aloud_is_answered_in_writing_only(
    synthesis: AsyncMock, message: Any, voice_enabled: bool
) -> None:
    sender = _sender()

    await _turn(message(), sender, voice_enabled=voice_enabled)

    assert sender.order == ["text"]
    synthesis.assert_not_awaited()


async def test_a_question_stays_written(synthesis: AsyncMock) -> None:
    """Its buttons answer it: a voice under it would read as the answer."""
    sender = _sender()
    question = (
        ChatStreamChunk(
            type="hitl_interrupt_metadata",
            content="",
            metadata={"message_id": "hitl_c_1", "action_requests": [{"type": "clarification"}]},
        ),
        ChatStreamChunk(type="hitl_question_token", content="Which city?", metadata={}),
    )

    await _turn(_voice_note(), sender, *question)

    synthesis.assert_not_awaited()
    sender.send_voice.assert_not_awaited()


async def test_a_voice_that_cannot_be_made_leaves_the_answer_as_written(
    synthesis: AsyncMock,
) -> None:
    synthesis.side_effect = RuntimeError("tts provider away")
    sender = _sender()

    await _turn(_voice_note(), sender)

    assert sender.order == ["text"]


async def test_an_answer_to_a_question_that_expired_is_told_in_writing(
    synthesis: AsyncMock,
) -> None:
    """The question changed while the person spoke: the notice is no answer to hear."""
    sender = _sender()

    await _turn(_voice_note(), sender, pending_hitl={"run_id": "run-asked"})

    assert sender.order == ["text"]
    synthesis.assert_not_awaited()
