"""Files in a channel turn, both ways (Telegram lot 11).

A photo or a document is the turn's attachment, its caption its words (its names
when it has none); a refusal is said and runs no turn; files sent while LIA works
cannot wait and are not kept. What the turn made leaves after its answer — before
its question, which stays last with its buttons.

Through the real gateway, the engine substituted (as ``test_inbound_handler``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.core.config import settings
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.attachments.urls import attachment_url
from src.domains.channels import inbound_handler
from src.domains.channels.abstractions import ChannelFile, ChannelFileKind, ChannelInboundMessage
from src.domains.channels.channel_files import FileRefusal, file_words
from src.domains.channels.inbound_handler import InboundMessageHandler
from src.domains.channels.models import ChannelType
from src.infrastructure.channels.telegram.formatter import get_bot_message
from tests.fixtures.instruction_runtime import instruction_runtime

pytestmark = pytest.mark.unit

#: The person's language — never the instance's, so nothing passes by falling back.
_PERSON = next(code for code in ("it", "es") if code != settings.default_language)
_PHOTO = ChannelFile("p1", ChannelFileKind.PHOTO, "photo.jpg", "image/jpeg", 10)


def _message(text: str | None = None, *files: ChannelFile) -> ChannelInboundMessage:
    return ChannelInboundMessage(
        channel_type=ChannelType.TELEGRAM,
        channel_user_id="12345",
        text=text,
        files=files or (_PHOTO,),
        message_id="5",
        raw_data={},
    )


class _Files:
    """The channel's file doors, recorded."""

    def __init__(self) -> None:
        self.received: tuple[UUID, ...] | FileRefusal = (uuid4(),)
        self.forgotten: list[tuple[UUID, ...]] = []
        self.made: list[tuple[UUID, ...]] = []
        self.order: list[str] = []

    async def receive(self, files: Any, *, user_id: UUID) -> tuple[UUID, ...] | FileRefusal:
        return self.received

    async def forget(self, ids: Any, *, user_id: UUID) -> None:
        self.forgotten.append(tuple(ids))

    async def send_made(self, _sender: Any, _chat: str, **kwargs: Any) -> None:
        self.made.append(tuple(kwargs["attachment_ids"]))
        self.order.append("files")


@pytest.fixture
def files() -> Iterator[_Files]:
    recorded = _Files()
    with (
        patch.object(inbound_handler, "receive_files", recorded.receive),
        patch.object(inbound_handler, "forget_files", recorded.forget),
        patch.object(inbound_handler, "send_generated_files", recorded.send_made),
    ):
        yield recorded


def _sender(recorded: _Files) -> AsyncMock:
    async def send(_chat: str, outbound: Any) -> str:
        recorded.order.append(outbound.text)
        return "1"

    return AsyncMock(send_message=AsyncMock(side_effect=send), send_typing_indicator=AsyncMock())


async def _turn(
    message: ChannelInboundMessage, sender: AsyncMock, *chunks: ChatStreamChunk
) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []

    async def response(**engine: Any) -> AsyncIterator[ChatStreamChunk]:
        seen.append(engine)
        for chunk in chunks or (ChatStreamChunk(type="token", content="ok"),):
            yield chunk

    owner = uuid4()
    with (
        instruction_runtime(owner),
        patch(
            "src.domains.agents.api.hitl_pending.check_pending_hitl_uncached",
            AsyncMock(return_value=None),
        ),
        patch("src.domains.agents.api.service.AgentService") as service,
        patch(
            "src.infrastructure.channels.telegram.formatter.markdown_to_telegram_html",
            side_effect=lambda text, language=None: text,
        ),
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
            user_voice_enabled=False,
            user_execution_mode="pipeline",
            conversation_id="conv-1",
            pending_hitl=None,
        )
    return seen


async def test_received_files_are_the_turn_s_attachments_its_caption_its_words(
    files: _Files,
) -> None:
    [engine] = await _turn(_message("what is this?"), _sender(files))

    assert engine["attachment_ids"] == list(files.received)
    assert engine["user_message"] == "what is this?"


async def test_files_sent_without_words_are_named() -> None:
    recorded = _Files()
    with (
        patch.object(inbound_handler, "receive_files", recorded.receive),
        patch.object(inbound_handler, "send_generated_files", recorded.send_made),
    ):
        [engine] = await _turn(_message(None), _sender(recorded))

    assert engine["user_message"] == file_words((_PHOTO,))


@pytest.mark.parametrize("refusal", list(FileRefusal))
async def test_files_that_cannot_be_received_are_said_and_run_no_turn(
    refusal: FileRefusal, files: _Files
) -> None:
    files.received = refusal
    sender = _sender(files)

    seen = await _turn(_message("look"), sender)

    assert seen == []
    expected = get_bot_message(f"files_{refusal.value}", _PERSON).format(
        limit=settings.attachments_max_per_message
    )
    assert files.order == [expected]


async def test_what_the_turn_made_leaves_after_its_answer(files: _Files) -> None:
    image = uuid4()
    done = ChatStreamChunk(
        type="done",
        content="",
        metadata={"generated_images": [{"url": attachment_url(image), "alt_text": "x"}]},
    )
    sender = _sender(files)

    await _turn(_message("draw it"), sender, ChatStreamChunk(type="token", content="Here."), done)

    assert files.made == [(image,)]
    assert files.order == ["Here.", "files"]


async def test_a_turn_that_made_nothing_sends_no_file(files: _Files) -> None:
    await _turn(_message("hello"), _sender(files))

    assert files.made == []


async def test_what_the_turn_made_leaves_before_its_question(files: _Files) -> None:
    """The question stays last: its buttons answer it, not the file under it."""
    image = uuid4()
    question = [
        ChatStreamChunk(
            type="hitl_interrupt_metadata",
            content="",
            metadata={"message_id": "hitl_c_1", "action_requests": [{"type": "draft_critique"}]},
        ),
        ChatStreamChunk(type="hitl_question_token", content="Send it?", metadata={}),
        ChatStreamChunk(
            type="done",
            content="",
            metadata={"generated_images": [{"url": attachment_url(image), "alt_text": "x"}]},
        ),
    ]

    await _turn(_message("draw and send it"), _sender(files), *question)

    assert files.made == [(image,)]
    assert files.order[0] == "files" and "Send it?" in files.order[1]
