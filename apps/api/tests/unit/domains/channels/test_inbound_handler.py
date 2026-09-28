"""Tests for InboundMessageHandler."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Literal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from prometheus_client import REGISTRY

from src.core.config import settings
from src.core.i18n import resolve_language
from src.domains.agents.api.error_messages import SSEErrorMessages
from src.domains.agents.api.hitl_pending import HITL_DECISION_STALE_ERROR_CODE
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.services.hitl.interactions.text_tokens import text_tokens
from src.domains.channels.abstractions import ChannelInboundMessage, ChannelOutboundMessage
from src.domains.channels.inbound_handler import InboundMessageHandler, interaction_type_of
from src.domains.channels.models import ChannelType
from src.infrastructure.channels.telegram.formatter import get_bot_message
from src.infrastructure.channels.telegram.hitl_keyboard import (
    get_button_label,
    question_fingerprint,
)

# Patch targets — source modules (lazy imports inside functions)
_PATCH_AGENT_SERVICE = "src.domains.agents.api.service.AgentService"
_PATCH_BOT_MESSAGE = "src.infrastructure.channels.telegram.formatter.get_bot_message"
_PATCH_MD_TO_HTML = "src.infrastructure.channels.telegram.formatter.markdown_to_telegram_html"

#: The chunk types these tests feed — each one the engine really emits.
_ChunkType = Literal[
    "token",
    "content_replacement",
    "hitl_interrupt_metadata",
    "hitl_question_token",
    "hitl_interrupt_complete",
    "error",
    "done",
]

#: A question's message id, as the streaming service writes it.
_QUESTION_ID = "hitl_conv-1_interrupt-1"


@pytest.fixture
def mock_sender() -> AsyncMock:
    sender = AsyncMock()
    sender.send_message = AsyncMock(return_value="msg_1")
    sender.send_typing_indicator = AsyncMock()
    return sender


@pytest.fixture
def handler(mock_sender: AsyncMock) -> InboundMessageHandler:
    return InboundMessageHandler(sender=mock_sender)


@pytest.fixture
def text_message() -> ChannelInboundMessage:
    return ChannelInboundMessage(
        channel_type=ChannelType.TELEGRAM,
        channel_user_id="12345",
        text="What is the weather?",
        message_id="42",
        raw_data={},
    )


@pytest.fixture
def voice_message() -> ChannelInboundMessage:
    return ChannelInboundMessage(
        channel_type=ChannelType.TELEGRAM,
        channel_user_id="12345",
        voice_file_id="voice_abc",
        voice_duration_seconds=5,
        message_id="43",
        raw_data={},
    )


def _make_chunk(
    chunk_type: _ChunkType, content: str = "", metadata: dict[str, object] | None = None
) -> ChatStreamChunk:
    """A real chunk: the wire contract validates its type."""
    return ChatStreamChunk(type=chunk_type, content=content, metadata=metadata)


async def _mock_stream(*chunks: ChatStreamChunk) -> AsyncIterator[ChatStreamChunk]:
    """Create an async generator yielding chunks."""
    for chunk in chunks:
        yield chunk


class _Engine:
    """The engine's stream, with the TAIL the streaming service runs after its
    last chunk — where it saves the pending question and commits the tokens."""

    def __init__(self, *chunks: ChatStreamChunk) -> None:
        self.chunks = chunks
        self.tail_ran = False

    async def stream(self, **_kwargs: object) -> AsyncIterator[ChatStreamChunk]:
        for chunk in self.chunks:
            yield chunk
        self.tail_ran = True


def _question(
    interaction: str,
    question: str = "Shall I send it?",
    *,
    message_id: str = _QUESTION_ID,
    completed_with: str | None = None,
) -> list[ChatStreamChunk]:
    """A question exactly as the streaming service emits it (``_handle_hitl_interrupt``).

    Args:
        interaction: The type the interaction writes in its first action request.
        question: The question, streamed as ``hitl_question_token`` chunks.
        message_id: The question's message id.
        completed_with: The ``generated_question`` of the completion chunk
            (the streamed question when None).
    """
    return [
        _make_chunk(
            "hitl_interrupt_metadata",
            metadata={"message_id": message_id, "action_requests": [{"type": interaction}]},
        ),
        *(
            _make_chunk("hitl_question_token", token, {"message_id": message_id})
            for token in text_tokens(question)
        ),
        _make_chunk(
            "hitl_interrupt_complete",
            metadata={
                "message_id": message_id,
                "requires_approval": True,
                "generated_question": question if completed_with is None else completed_with,
            },
        ),
    ]


def _questions_counted(interaction: str) -> float:
    return (
        REGISTRY.get_sample_value(
            "channel_hitl_decisions_total",
            {"channel_type": "telegram", "decision": interaction},
        )
        or 0.0
    )


async def _handle(
    handler: InboundMessageHandler,
    message: ChannelInboundMessage,
    *,
    conversation_id: str | None = "conv-1",
    language: str = "fr",
    pending_hitl: dict[str, object] | None = None,
    hitl_decision: dict[str, str] | None = None,
) -> None:
    await handler.handle(
        message=message,
        user_id=uuid4(),
        user_language=language,
        user_timezone="Europe/Paris",
        user_memory_enabled=True,
        user_journals_enabled=True,
        user_psyche_enabled=True,
        conversation_id=conversation_id,
        pending_hitl=pending_hitl,
        hitl_decision=hitl_decision,
    )


def _sent(sender: AsyncMock) -> ChannelOutboundMessage:
    """The one message the person got."""
    sender.send_message.assert_awaited_once()
    outbound: ChannelOutboundMessage = sender.send_message.await_args.args[1]
    return outbound


# =============================================================================
# Text message handling
# =============================================================================


class TestTextMessageHandling:
    """Tests for processing text messages through the agent pipeline."""

    @pytest.mark.asyncio
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)  # passthrough
    @patch(_PATCH_AGENT_SERVICE)
    async def test_collects_tokens_and_sends_response(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        handler: InboundMessageHandler,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """Should collect streamed tokens and send formatted response."""
        chunks = [
            _make_chunk("token", "Hello "),
            _make_chunk("token", "world!"),
            _make_chunk("done", ""),
        ]

        mock_agent = mock_agent_cls.return_value
        mock_agent.stream_chat_response = MagicMock(return_value=_mock_stream(*chunks))

        await _handle(handler, text_message, conversation_id=None)

        assert _sent(mock_sender).text == "Hello world!"

    @pytest.mark.asyncio
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_the_stream_runs_on_a_plain_surface(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        handler: InboundMessageHandler,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """A channel renders no card (ADR-289): the draft question and the
        execution result must be drawn as text for the whole stream, and the
        declaration must not outlive the stream."""
        from src.domains.agents.api.run_origin import plain_surface_ctx

        seen: list[bool] = []

        async def _observing_stream(**_kwargs: object) -> AsyncIterator[ChatStreamChunk]:
            seen.append(plain_surface_ctx.get())
            yield _make_chunk("token", "ok")
            yield _make_chunk("done", "")
            seen.append(plain_surface_ctx.get())

        mock_agent = mock_agent_cls.return_value
        mock_agent.stream_chat_response = MagicMock(side_effect=_observing_stream)

        await _handle(handler, text_message, conversation_id=None)

        assert seen == [True, True]
        assert plain_surface_ctx.get() is False

    @pytest.mark.asyncio
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_empty_response_not_sent(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        handler: InboundMessageHandler,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """Empty agent response should not trigger a send."""
        chunks = [_make_chunk("done", "")]
        mock_agent = mock_agent_cls.return_value
        mock_agent.stream_chat_response = MagicMock(return_value=_mock_stream(*chunks))

        await _handle(handler, text_message, conversation_id=None)

        mock_sender.send_message.assert_not_called()

    @pytest.mark.asyncio
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_session_id_includes_channel_type_and_user_id(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        handler: InboundMessageHandler,
        text_message: ChannelInboundMessage,
    ) -> None:
        """Session ID should be 'channel_telegram_{user_id}'."""
        chunks = [_make_chunk("done", "")]
        mock_agent = mock_agent_cls.return_value
        mock_agent.stream_chat_response = MagicMock(return_value=_mock_stream(*chunks))

        user_id = uuid4()
        await handler.handle(
            message=text_message,
            user_id=user_id,
            user_language="en",
            user_timezone="America/New_York",
            user_memory_enabled=False,
            user_journals_enabled=True,
            user_psyche_enabled=True,
            conversation_id=None,
            pending_hitl=None,
        )

        call_kwargs = mock_agent.stream_chat_response.call_args[1]
        assert call_kwargs["session_id"] == f"channel_telegram_{user_id}"
        assert call_kwargs["user_language"] == "en"
        assert call_kwargs["user_timezone"] == "America/New_York"
        assert call_kwargs["user_memory_enabled"] is False

    @pytest.mark.asyncio
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_the_stream_is_read_to_its_end_past_the_done_chunk(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        handler: InboundMessageHandler,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """The service closes the turn's clients AFTER its ``done`` chunk: a
        reader that left there closed the generator before they were."""
        engine = _Engine(_make_chunk("token", "Hello"), _make_chunk("done", ""))
        mock_agent_cls.return_value.stream_chat_response = MagicMock(side_effect=engine.stream)

        await _handle(handler, text_message, conversation_id=None)

        assert engine.tail_ran
        assert _sent(mock_sender).text == "Hello"

    @pytest.mark.asyncio
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_a_refusal_s_technical_text_never_reaches_the_person(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        handler: InboundMessageHandler,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """A usage refusal carries technical text the chat localises from its
        code: the channel logs the code and sends none of the text."""
        from structlog.testing import capture_logs

        chunks = [
            _make_chunk("error", "Usage limit exceeded", {"error_code": "usage_limit_exceeded"}),
        ]
        mock_agent_cls.return_value.stream_chat_response = MagicMock(
            return_value=_mock_stream(*chunks)
        )

        with capture_logs() as logs:
            await _handle(handler, text_message, conversation_id=None)

        mock_sender.send_message.assert_not_called()
        (logged,) = [e for e in logs if e["event"] == "channel_inbound_stream_error"]
        assert logged["error_code"] == "usage_limit_exceeded"
        assert "Usage limit exceeded" not in str(logged)

    @pytest.mark.asyncio
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_a_decision_its_question_no_longer_matches_is_told_expired(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        handler: InboundMessageHandler,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """The engine refuses a structured decision whose question moved on
        (``hitl_stale_chunks``): the person is told « expired », in their
        language, as the chat's card flips to its expired state."""
        person = next(code for code in ("it", "es") if code != settings.default_language)
        chunks = [
            _make_chunk(
                "error",
                SSEErrorMessages.hitl_decision_stale(language="fr"),
                {"error_code": HITL_DECISION_STALE_ERROR_CODE},
            ),
            _make_chunk("done", ""),
        ]
        mock_agent_cls.return_value.stream_chat_response = MagicMock(
            return_value=_mock_stream(*chunks)
        )

        await _handle(
            handler,
            text_message,
            language=person,
            hitl_decision={"message_id": _QUESTION_ID, "action": "confirm"},
        )

        assert _sent(mock_sender).text == get_bot_message("hitl_expired", person)


# =============================================================================
# Voice message handling (not yet implemented)
# =============================================================================


class TestVoiceMessage:
    """Tests for voice messages."""

    @pytest.mark.asyncio
    @patch(_PATCH_AGENT_SERVICE)
    async def test_voice_transcription_failure_returns_early(
        self,
        mock_agent_cls: MagicMock,
        handler: InboundMessageHandler,
        mock_sender: AsyncMock,
        voice_message: ChannelInboundMessage,
    ) -> None:
        """Failed voice transcription should return early without calling agent."""
        with patch.object(handler, "_transcribe_voice", new_callable=AsyncMock, return_value=None):
            await _handle(handler, voice_message, conversation_id=None)

        # handle() returns early when _transcribe_voice returns None:
        # no agent pipeline call, no send_message from handle()
        mock_agent_cls.assert_not_called()
        mock_sender.send_message.assert_not_called()

    @pytest.mark.asyncio
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_voice_transcription_success_calls_agent(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        handler: InboundMessageHandler,
        mock_sender: AsyncMock,
        voice_message: ChannelInboundMessage,
    ) -> None:
        """Successful voice transcription should proceed to agent pipeline."""
        chunks = [
            _make_chunk("token", "Voice response"),
            _make_chunk("done", ""),
        ]
        mock_agent = mock_agent_cls.return_value
        mock_agent.stream_chat_response = MagicMock(return_value=_mock_stream(*chunks))

        with patch.object(
            handler, "_transcribe_voice", new_callable=AsyncMock, return_value="Transcribed text"
        ):
            await _handle(handler, voice_message, conversation_id=None)

        # Agent was called with transcribed text
        call_kwargs = mock_agent.stream_chat_response.call_args[1]
        assert call_kwargs["user_message"] == "Transcribed text"
        # Response sent to user
        mock_sender.send_message.assert_called_once()


# =============================================================================
# HITL response handling
# =============================================================================


class TestHITLResponse:
    """Tests for handling messages when HITL is pending."""

    @pytest.mark.asyncio
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_hitl_response_passes_original_run_id(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        handler: InboundMessageHandler,
        text_message: ChannelInboundMessage,
    ) -> None:
        """When HITL is pending, the run its question was asked on is resumed.

        The shape is ``HITLStore.get_pending``'s: the one this test froze
        (``interrupt_data.original_run_id``) no writer ever wrote (review 12)."""
        chunks = [
            _make_chunk("token", "Plan approved."),
            _make_chunk("done", ""),
        ]
        mock_agent = mock_agent_cls.return_value
        mock_agent.stream_chat_response = MagicMock(return_value=_mock_stream(*chunks))

        pending_hitl: dict[str, object] = {
            "action_requests": [{"type": "plan_approval"}],
            "count": 1,
            "run_id": "run_xyz_123",
            "interrupt_ts": "2026-03-03T00:00:00+00:00",
        }

        await _handle(handler, text_message, conversation_id="conv-789", pending_hitl=pending_hitl)

        call_kwargs = mock_agent.stream_chat_response.call_args[1]
        assert call_kwargs["original_run_id"] == "run_xyz_123"

    @pytest.mark.asyncio
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_no_hitl_passes_none_run_id(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        handler: InboundMessageHandler,
        text_message: ChannelInboundMessage,
    ) -> None:
        """Without pending HITL, original_run_id should be None."""
        chunks = [_make_chunk("done", "")]
        mock_agent = mock_agent_cls.return_value
        mock_agent.stream_chat_response = MagicMock(return_value=_mock_stream(*chunks))

        await _handle(handler, text_message, conversation_id=None)

        call_kwargs = mock_agent.stream_chat_response.call_args[1]
        assert call_kwargs["original_run_id"] is None

    @pytest.mark.asyncio
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_an_answer_resumes_under_the_run_its_question_was_asked_on(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        handler: InboundMessageHandler,
        text_message: ChannelInboundMessage,
    ) -> None:
        """Saved the way the streaming service saves it, read the way the channel
        doors read it: the answer is billed and registered under the run that
        asked, as in the chat — never under a fresh one (review 12)."""
        from src.core.constants import REDIS_CACHE_DB
        from src.core.field_names import FIELD_ACTION_REQUESTS, FIELD_RUN_ID
        from src.domains.agents.utils.hitl_store import HITLStore
        from src.domains.channels.message_router import read_pending_question
        from tests.helpers.redis_databases import RedisServer

        engine_cache = RedisServer().client(REDIS_CACHE_DB)
        await HITLStore(redis_client=engine_cache, ttl_seconds=60).save_interrupt(
            "conv-789",
            {
                FIELD_ACTION_REQUESTS: [{"type": "plan_approval"}],
                "count": 1,
                FIELD_RUN_ID: "run-asked",
                "interrupt_ts": "1758844800.0",
                "message_id": "msg-1",
                "generated_question": "Shall I?",
            },
        )
        mock_agent = mock_agent_cls.return_value
        mock_agent.stream_chat_response = MagicMock(
            return_value=_mock_stream(_make_chunk("done", ""))
        )
        with patch(
            "src.infrastructure.cache.redis.get_redis_cache",
            new=AsyncMock(return_value=engine_cache),
        ):
            pending = await read_pending_question("conv-789")

        await _handle(handler, text_message, conversation_id="conv-789", pending_hitl=pending)

        assert mock_agent.stream_chat_response.call_args.kwargs["original_run_id"] == "run-asked"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("run_id", [None, "", 42], ids=["absent", "empty", "not_a_string"])
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_a_question_with_no_usable_run_resumes_under_a_fresh_one(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        run_id: object,
        handler: InboundMessageHandler,
        text_message: ChannelInboundMessage,
    ) -> None:
        """What the store holds is read, never trusted: a run id it cannot
        use leaves the service to mint one, as the voice delegation does
        (``voice_delegation._resumption``)."""
        pending: dict[str, object] = {"action_requests": [{"type": "clarification"}]}
        if run_id is not None:
            pending["run_id"] = run_id
        mock_agent = mock_agent_cls.return_value
        mock_agent.stream_chat_response = MagicMock(
            return_value=_mock_stream(_make_chunk("done", ""))
        )

        await _handle(handler, text_message, conversation_id="conv-789", pending_hitl=pending)

        assert mock_agent.stream_chat_response.call_args.kwargs["original_run_id"] is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "decision",
        [None, {"message_id": _QUESTION_ID, "action": "confirm"}],
        ids=["typed_answer", "button"],
    )
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_a_button_s_decision_reaches_the_engine_as_the_card_s(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        decision: dict[str, str] | None,
        handler: InboundMessageHandler,
        text_message: ChannelInboundMessage,
    ) -> None:
        """A press resumes its question on the structured decision, applied
        without a model; a typed answer carries none and is read as words."""
        mock_agent = mock_agent_cls.return_value
        mock_agent.stream_chat_response = MagicMock(
            return_value=_mock_stream(_make_chunk("done", ""))
        )

        await _handle(
            handler,
            text_message,
            pending_hitl={"action_requests": [{"type": "draft_critique"}], "run_id": "run-1"},
            hitl_decision=decision,
        )

        assert mock_agent.stream_chat_response.call_args.kwargs["hitl_decision"] == decision


# =============================================================================
# HITL interrupt detection during streaming
# =============================================================================


class TestHITLInterruptDetection:
    """A question reaches the person as the engine streams it (review 14)."""

    @pytest.mark.asyncio
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_the_question_is_what_the_person_reads(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        handler: InboundMessageHandler,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """The question travels as ``hitl_question_token`` chunks and in the
        completion's ``generated_question`` — never as ``token``: read from the
        answer's tokens, every question went out EMPTY, and Telegram refuses an
        empty message. What the answer streamed before is not the question."""
        chunks = [_make_chunk("token", "Thinking…"), *_question("draft_critique")]
        mock_agent_cls.return_value.stream_chat_response = MagicMock(
            return_value=_mock_stream(*chunks)
        )

        await _handle(handler, text_message)

        assert _sent(mock_sender).text == "Shall I send it?"

    @pytest.mark.asyncio
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_the_completion_s_question_wins_over_its_deltas(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        handler: InboundMessageHandler,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """The completion carries the question the stream settled on."""
        chunks = _question("draft_critique", "Shall I", completed_with="Shall I send it?")
        mock_agent_cls.return_value.stream_chat_response = MagicMock(
            return_value=_mock_stream(*chunks)
        )

        await _handle(handler, text_message)

        assert _sent(mock_sender).text == "Shall I send it?"

    @pytest.mark.asyncio
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_a_question_the_completion_left_empty_is_its_deltas(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        handler: InboundMessageHandler,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        chunks = _question("draft_critique", "Shall I send it?", completed_with="")
        mock_agent_cls.return_value.stream_chat_response = MagicMock(
            return_value=_mock_stream(*chunks)
        )

        await _handle(handler, text_message)

        assert _sent(mock_sender).text == "Shall I send it?"

    @pytest.mark.asyncio
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_a_question_the_stream_left_empty_is_the_engine_s_last_resort(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        handler: InboundMessageHandler,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """Never an empty message under a keyboard: the Bot API refuses it, and
        the person's next words would answer a question they never saw."""
        person = next(code for code in ("it", "es") if code != settings.default_language)
        chunks = _question("draft_critique", "", completed_with="")
        mock_agent_cls.return_value.stream_chat_response = MagicMock(
            return_value=_mock_stream(*chunks)
        )

        await _handle(handler, text_message, language=person)

        assert _sent(mock_sender).text == SSEErrorMessages.confirmation_required(
            language=resolve_language(person)
        )

    @pytest.mark.asyncio
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_the_question_leaves_once_the_engine_saved_it(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        handler: InboundMessageHandler,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """The streaming service saves the pending question AFTER its completion
        chunk: a reader that left at the question closed the generator first,
        so no question asked on Telegram was ever saved, and a press found none
        (review 14). The stream is read to its end, then the question sent."""
        engine = _Engine(*_question("draft_critique"))
        seen_saved: list[bool] = []

        async def _send(_chat: str, _outbound: ChannelOutboundMessage) -> str:
            seen_saved.append(engine.tail_ran)
            return "msg_1"

        mock_sender.send_message = AsyncMock(side_effect=_send)
        mock_agent_cls.return_value.stream_chat_response = MagicMock(side_effect=engine.stream)

        await _handle(handler, text_message)

        assert seen_saved == [True]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("interaction", "buttons"),
        [
            ("for_each_confirmation", ["continue", "stop"]),
            ("draft_critique", ["confirm", "cancel"]),
            ("tool_confirmation", ["confirm", "cancel"]),
            ("clarification", None),
            ("entity_disambiguation", None),
        ],
    )
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_the_keyboard_is_the_one_its_interaction_draws(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        interaction: str,
        buttons: list[str] | None,
        handler: InboundMessageHandler,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """The type is read where the interactions write it
        (``action_requests[0]["type"]``): a top-level key nobody wrote drew
        Approve / Reject under every question, a clarification included. Each
        button names the conversation and THE question it answers."""
        mock_agent_cls.return_value.stream_chat_response = MagicMock(
            return_value=_mock_stream(*_question(interaction))
        )

        await _handle(handler, text_message)

        markup = _sent(mock_sender).reply_markup
        drawn = (
            [button["callback_data"] for button in markup["inline_keyboard"][0]] if markup else None
        )
        mark = question_fingerprint(_QUESTION_ID)
        assert drawn == (
            None if buttons is None else [f"hitl:{action}:conv-1:{mark}" for action in buttons]
        )

    @pytest.mark.asyncio
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_the_keyboard_speaks_the_person_s_language(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        handler: InboundMessageHandler,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        person = next(code for code in ("it", "es") if code != settings.default_language)
        mock_agent_cls.return_value.stream_chat_response = MagicMock(
            return_value=_mock_stream(*_question("draft_critique"))
        )

        await _handle(handler, text_message, language=person)

        markup = _sent(mock_sender).reply_markup
        assert markup is not None
        assert [button["text"] for button in markup["inline_keyboard"][0]] == [
            get_button_label("confirm", person),
            get_button_label("cancel", person),
        ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("conversation_id", "message_id"),
        [(None, _QUESTION_ID), ("conv-1", "")],
        ids=["no_conversation", "no_question_id"],
    )
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_no_keyboard_names_what_it_cannot(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        conversation_id: str | None,
        message_id: str,
        handler: InboundMessageHandler,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """A button names its conversation and its question: without either,
        a press could answer nothing, so the question goes out to be answered
        in words."""
        mock_agent_cls.return_value.stream_chat_response = MagicMock(
            return_value=_mock_stream(*_question("draft_critique", message_id=message_id))
        )

        await _handle(handler, text_message, conversation_id=conversation_id)

        sent = _sent(mock_sender)
        assert sent.reply_markup is None
        assert sent.text == "Shall I send it?"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("sent_id", ["msg_1", None], ids=["taken", "refused"])
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_a_question_is_counted_once_telegram_took_it(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        sent_id: str | None,
        handler: InboundMessageHandler,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """The metric counts questions SENT, by interaction: a question Telegram
        refused was counted and logged as sent with its keyboard."""
        from structlog.testing import capture_logs

        mock_sender.send_message = AsyncMock(return_value=sent_id)
        mock_agent_cls.return_value.stream_chat_response = MagicMock(
            return_value=_mock_stream(*_question("tool_confirmation"))
        )
        before = _questions_counted("tool_confirmation")

        with capture_logs() as logs:
            await _handle(handler, text_message)

        events = [entry["event"] for entry in logs]
        if sent_id is None:
            assert _questions_counted("tool_confirmation") == before
            assert "channel_hitl_question_unsent" in events
            assert "channel_hitl_keyboard_sent" not in events
        else:
            assert _questions_counted("tool_confirmation") == before + 1
            assert "channel_hitl_keyboard_sent" in events


class TestInteractionTypeOf:
    """The interaction is read where every interaction writes it."""

    def test_the_first_action_request_names_it(self) -> None:
        metadata = {
            "type": "plan_approval",
            "action_requests": [{"type": "clarification"}, {"type": "draft_critique"}],
        }

        assert interaction_type_of(metadata) == "clarification"

    @pytest.mark.parametrize(
        "metadata",
        [
            {"type": "plan_approval"},
            {"action_requests": []},
            {"action_requests": ["draft_critique"]},
            {"action_requests": [{"type": ""}]},
            {"action_requests": [{"type": 3}]},
        ],
    )
    def test_metadata_naming_no_interaction_is_unknown(self, metadata: dict[str, object]) -> None:
        """Never a plan approval by default: a default drew Approve / Reject under
        every question and counted each as a plan approval."""
        assert interaction_type_of(metadata) == "unknown"


# =============================================================================
# Typing indicator
# =============================================================================


class TestTypingIndicator:
    """Tests for continuous typing indicator."""

    @pytest.mark.asyncio
    async def test_continuous_typing_calls_sender(
        self,
        handler: InboundMessageHandler,
        mock_sender: AsyncMock,
    ) -> None:
        """_continuous_typing should call send_typing_indicator repeatedly."""
        task = asyncio.create_task(handler._continuous_typing("12345"))
        # Let it run one iteration
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        mock_sender.send_typing_indicator.assert_called_with("12345")

    @pytest.mark.asyncio
    async def test_continuous_typing_handles_cancellation(
        self,
        handler: InboundMessageHandler,
        mock_sender: AsyncMock,
    ) -> None:
        """_continuous_typing should handle CancelledError gracefully."""
        task = asyncio.create_task(handler._continuous_typing("12345"))
        await asyncio.sleep(0.01)
        task.cancel()
        # Should not raise — CancelledError is caught
        await task


# =============================================================================
# Content replacement, HTML stripping, and error handling
# =============================================================================


class TestContentReplacementAndErrors:
    """Tests for content_replacement deduplication, HTML stripping, and error handling."""

    @pytest.mark.asyncio
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_content_replacement_replaces_tokens(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        handler: InboundMessageHandler,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """content_replacement is the authoritative source — should replace tokens."""
        # Simulate the real issue: tokens contain duplicated text + HTML
        # (incremental tokens + final AIMessage re-emitted as a token)
        html_content = 'Hello world!\n\n<div class="weather-card">22°C sunny</div>'
        chunks = [
            _make_chunk("token", "Hello "),
            _make_chunk("token", "world!"),
            # content_replacement contains full text + HTML (authoritative)
            _make_chunk("content_replacement", html_content),
            _make_chunk("done", ""),
        ]
        mock_agent = mock_agent_cls.return_value
        mock_agent.stream_chat_response = MagicMock(return_value=_mock_stream(*chunks))

        await _handle(handler, text_message, conversation_id=None)

        sent_msg = _sent(mock_sender)
        # content_replacement (HTML-stripped) is used, not the raw tokens
        assert "Hello world!" in sent_msg.text
        assert "<div" not in sent_msg.text
        assert "weather-card" not in sent_msg.text
        # Crucially: text should NOT be duplicated
        assert sent_msg.text.count("Hello world!") == 1

    @pytest.mark.asyncio
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_content_replacement_deduplicates_real_scenario(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        handler: InboundMessageHandler,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """Real scenario: tokens contain text twice, content_replacement has it once."""
        # Reproduce the exact bug: LangGraph emits incremental tokens then
        # the full final AIMessage (with HTML) as another set of tokens.
        llm_text = "La météo demain sera ensoleillée, 22°C."
        html_card = '\n\n<div class="weather-card"><span>22°C</span></div>'
        chunks = [
            # Incremental tokens (first copy)
            _make_chunk("token", "La météo "),
            _make_chunk("token", "demain sera "),
            _make_chunk("token", "ensoleillée, 22°C."),
            # Final AIMessage re-emitted as token (second copy + HTML)
            _make_chunk("token", llm_text + html_card),
            # Authoritative content_replacement
            _make_chunk("content_replacement", llm_text + html_card),
            _make_chunk("done", ""),
        ]
        mock_agent = mock_agent_cls.return_value
        mock_agent.stream_chat_response = MagicMock(return_value=_mock_stream(*chunks))

        await _handle(handler, text_message, conversation_id=None)

        sent_msg = _sent(mock_sender)
        # Text should appear exactly once (no duplication)
        assert sent_msg.text.count("La météo demain") == 1
        # No HTML cards
        assert "<div" not in sent_msg.text
        assert "</span>" not in sent_msg.text

    @pytest.mark.asyncio
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_content_replacement_fallback_when_no_tokens(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        handler: InboundMessageHandler,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """When no tokens collected, content_replacement (HTML-stripped) should be used."""
        html_content = 'Forecast for tomorrow: sunny.\n\n<div class="card">22°C</div>'
        chunks = [
            # No token chunks — edge case (LangGraph stream ordering)
            _make_chunk("content_replacement", html_content),
            _make_chunk("done", ""),
        ]
        mock_agent = mock_agent_cls.return_value
        mock_agent.stream_chat_response = MagicMock(return_value=_mock_stream(*chunks))

        await _handle(handler, text_message, conversation_id=None)

        sent_msg = _sent(mock_sender)
        assert "Forecast for tomorrow: sunny." in sent_msg.text
        assert "<div" not in sent_msg.text

    @pytest.mark.asyncio
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_html_stripped_from_token_stream(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        handler: InboundMessageHandler,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """HTML cards leaked into token stream should be stripped."""
        # Simulate edge-case: final AIMessage (with HTML) emitted as token
        chunks = [
            _make_chunk("token", "Weather forecast.\n\n"),
            _make_chunk("token", '<div class="card">22°C</div>'),
            _make_chunk("done", ""),
        ]
        mock_agent = mock_agent_cls.return_value
        mock_agent.stream_chat_response = MagicMock(return_value=_mock_stream(*chunks))

        await _handle(handler, text_message, conversation_id=None)

        sent_msg = _sent(mock_sender)
        assert "Weather forecast." in sent_msg.text
        assert "<div" not in sent_msg.text

    @pytest.mark.asyncio
    @patch(_PATCH_BOT_MESSAGE, return_value="Error message")
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_agent_error_sends_error_message(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        mock_bot_msg: MagicMock,
        handler: InboundMessageHandler,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """Agent pipeline crash should send error message to user."""
        mock_agent = mock_agent_cls.return_value
        mock_agent.stream_chat_response = MagicMock(side_effect=RuntimeError("Pipeline exploded"))

        await _handle(handler, text_message, conversation_id=None)

        # Error message sent (wrapped in ChannelOutboundMessage)
        assert _sent(mock_sender).text == "Error message"

    @pytest.mark.asyncio
    @patch(_PATCH_BOT_MESSAGE, return_value="Error message")
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_a_stream_that_fails_after_its_error_chunk_is_told(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        mock_bot_msg: MagicMock,
        handler: InboundMessageHandler,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """The service yields its error chunk, then raises: read to its end,
        the stream's failure reaches the person — a reader that stopped at the
        error chunk sent nothing at all."""

        async def _failing(**_kwargs: object) -> AsyncIterator[ChatStreamChunk]:
            yield _make_chunk("token", "partial ")
            yield _make_chunk("error", "Something went wrong", {"error_type": "stream_error"})
            raise RuntimeError("graph failed")

        mock_agent_cls.return_value.stream_chat_response = MagicMock(side_effect=_failing)

        await _handle(handler, text_message, conversation_id=None)

        assert _sent(mock_sender).text == "Error message"
