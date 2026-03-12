"""Tests for InboundMessageHandler."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.channels.abstractions import ChannelInboundMessage
from src.domains.channels.inbound_handler import InboundMessageHandler
from src.domains.channels.models import ChannelType

# Patch targets — source modules (lazy imports inside functions)
_PATCH_AGENT_SERVICE = "src.domains.agents.api.service.AgentService"
_PATCH_BOT_MESSAGE = "src.infrastructure.channels.telegram.formatter.get_bot_message"
_PATCH_MD_TO_HTML = "src.infrastructure.channels.telegram.formatter.markdown_to_telegram_html"


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


def _make_chunk(chunk_type: str, content: str = "", metadata: dict | None = None):
    """Create a mock ChatStreamChunk."""
    chunk = MagicMock()
    chunk.type = chunk_type
    chunk.content = content
    chunk.metadata = metadata
    return chunk


async def _mock_stream(*chunks):
    """Create an async generator yielding chunks."""
    for chunk in chunks:
        yield chunk


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

        user_id = uuid4()
        await handler.handle(
            message=text_message,
            user_id=user_id,
            user_language="fr",
            user_timezone="Europe/Paris",
            user_memory_enabled=True,
            conversation_id=None,
            pending_hitl=None,
        )

        # Response sent to user
        mock_sender.send_message.assert_called_once()
        sent_msg = mock_sender.send_message.call_args[0][1]
        assert sent_msg.text == "Hello world!"

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

        await handler.handle(
            message=text_message,
            user_id=uuid4(),
            user_language="fr",
            user_timezone="Europe/Paris",
            user_memory_enabled=True,
            conversation_id=None,
            pending_hitl=None,
        )

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
    async def test_error_chunk_stops_streaming(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        handler: InboundMessageHandler,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """Error chunk should stop token collection."""
        chunks = [
            _make_chunk("token", "partial "),
            _make_chunk("error", "something went wrong"),
            _make_chunk("token", "should not appear"),
        ]
        mock_agent = mock_agent_cls.return_value
        mock_agent.stream_chat_response = MagicMock(return_value=_mock_stream(*chunks))

        await handler.handle(
            message=text_message,
            user_id=uuid4(),
            user_language="fr",
            user_timezone="Europe/Paris",
            user_memory_enabled=True,
            conversation_id=None,
            pending_hitl=None,
        )

        # Only "partial " was collected before error
        sent_msg = mock_sender.send_message.call_args[0][1]
        assert "should not appear" not in sent_msg.text


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
            await handler.handle(
                message=voice_message,
                user_id=uuid4(),
                user_language="fr",
                user_timezone="Europe/Paris",
                user_memory_enabled=True,
                conversation_id=None,
                pending_hitl=None,
            )

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
            await handler.handle(
                message=voice_message,
                user_id=uuid4(),
                user_language="fr",
                user_timezone="Europe/Paris",
                user_memory_enabled=True,
                conversation_id=None,
                pending_hitl=None,
            )

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
        """When HITL is pending, original_run_id should be passed to stream_chat_response."""
        chunks = [
            _make_chunk("token", "Plan approved."),
            _make_chunk("done", ""),
        ]
        mock_agent = mock_agent_cls.return_value
        mock_agent.stream_chat_response = MagicMock(return_value=_mock_stream(*chunks))

        pending_hitl = {
            "schema_version": 1,
            "interrupt_ts": "2026-03-03T00:00:00",
            "interrupt_data": {
                "action_requests": [],
                "original_run_id": "run_xyz_123",
            },
        }

        await handler.handle(
            message=text_message,
            user_id=uuid4(),
            user_language="fr",
            user_timezone="Europe/Paris",
            user_memory_enabled=True,
            conversation_id="conv-789",
            pending_hitl=pending_hitl,
        )

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

        await handler.handle(
            message=text_message,
            user_id=uuid4(),
            user_language="fr",
            user_timezone="Europe/Paris",
            user_memory_enabled=True,
            conversation_id=None,
            pending_hitl=None,
        )

        call_kwargs = mock_agent.stream_chat_response.call_args[1]
        assert call_kwargs["original_run_id"] is None


# =============================================================================
# HITL interrupt detection during streaming
# =============================================================================


class TestHITLInterruptDetection:
    """Tests for detecting HITL interrupts during agent streaming."""

    @pytest.mark.asyncio
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_hitl_interrupt_stops_streaming(
        self,
        mock_agent_cls: MagicMock,
        mock_md_html: MagicMock,
        handler: InboundMessageHandler,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """HITL interrupt_complete should stop token collection."""
        chunks = [
            _make_chunk("token", "Here is "),
            _make_chunk("hitl_interrupt_metadata", "", metadata={"type": "plan_approval"}),
            _make_chunk("token", "the plan"),
            _make_chunk("hitl_interrupt_complete", ""),
            _make_chunk("token", "after interrupt"),  # Should not be collected
        ]
        mock_agent = mock_agent_cls.return_value
        mock_agent.stream_chat_response = MagicMock(return_value=_mock_stream(*chunks))

        await handler.handle(
            message=text_message,
            user_id=uuid4(),
            user_language="fr",
            user_timezone="Europe/Paris",
            user_memory_enabled=True,
            conversation_id=None,
            pending_hitl=None,
        )

        # Response should include tokens before the interrupt
        sent_msg = mock_sender.send_message.call_args[0][1]
        assert "Here is " in sent_msg.text
        assert "the plan" in sent_msg.text
        assert "after interrupt" not in sent_msg.text


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

        await handler.handle(
            message=text_message,
            user_id=uuid4(),
            user_language="fr",
            user_timezone="Europe/Paris",
            user_memory_enabled=True,
            conversation_id=None,
            pending_hitl=None,
        )

        sent_msg = mock_sender.send_message.call_args[0][1]
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

        await handler.handle(
            message=text_message,
            user_id=uuid4(),
            user_language="fr",
            user_timezone="Europe/Paris",
            user_memory_enabled=True,
            conversation_id=None,
            pending_hitl=None,
        )

        sent_msg = mock_sender.send_message.call_args[0][1]
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

        await handler.handle(
            message=text_message,
            user_id=uuid4(),
            user_language="fr",
            user_timezone="Europe/Paris",
            user_memory_enabled=True,
            conversation_id=None,
            pending_hitl=None,
        )

        sent_msg = mock_sender.send_message.call_args[0][1]
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

        await handler.handle(
            message=text_message,
            user_id=uuid4(),
            user_language="fr",
            user_timezone="Europe/Paris",
            user_memory_enabled=True,
            conversation_id=None,
            pending_hitl=None,
        )

        sent_msg = mock_sender.send_message.call_args[0][1]
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

        await handler.handle(
            message=text_message,
            user_id=uuid4(),
            user_language="fr",
            user_timezone="Europe/Paris",
            user_memory_enabled=True,
            conversation_id=None,
            pending_hitl=None,
        )

        # Error message sent (wrapped in ChannelOutboundMessage)
        mock_sender.send_message.assert_called_once()
        sent_msg = mock_sender.send_message.call_args[0][1]
        assert sent_msg.text == "Error message"
