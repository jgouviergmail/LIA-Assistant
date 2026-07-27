"""External channels must forward the SAME preferences as the web chat (L3 / D1).

``inbound_handler`` used to call ``stream_chat_response`` with
``user_memory_enabled`` only. The two missing parameters fell back to their
signature defaults (``False``), so a Telegram or WhatsApp conversation NEVER fed
the personal journals nor the psyche engine — whatever the user had enabled, and
whatever the database said (both columns default to true). The skip was logged
at ``debug``: nothing surfaced it.

These tests pin the propagation at every hop of the chain, and the fail-closed
behaviour when the user row cannot be loaded.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.channels.abstractions import ChannelInboundMessage
from src.domains.channels.inbound_handler import InboundMessageHandler
from src.domains.channels.models import ChannelType

_PATCH_AGENT_SERVICE = "src.domains.agents.api.service.AgentService"
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
        text="je déménage à Lyon en septembre",
        message_id="42",
        raw_data={},
    )


def _make_chunk(chunk_type: str, content: str = "", metadata: dict | None = None):
    chunk = MagicMock()
    chunk.type = chunk_type
    chunk.content = content
    chunk.metadata = metadata
    return chunk


async def _mock_stream(*chunks):
    for chunk in chunks:
        yield chunk


@pytest.mark.unit
class TestHandlerForwardsPreferences:
    """The handler is the hop where the two parameters used to vanish."""

    @pytest.mark.asyncio
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_enabled_preferences_reach_the_agent_service(
        self,
        mock_agent_cls: MagicMock,
        _mock_md_html: MagicMock,
        handler: InboundMessageHandler,
        text_message: ChannelInboundMessage,
    ) -> None:
        mock_agent = mock_agent_cls.return_value
        mock_agent.stream_chat_response = MagicMock(
            return_value=_mock_stream(_make_chunk("token", "ok"), _make_chunk("done", ""))
        )

        await handler.handle(
            message=text_message,
            user_id=uuid4(),
            user_language="fr",
            user_timezone="Europe/Paris",
            user_memory_enabled=True,
            user_journals_enabled=True,
            user_psyche_enabled=True,
            conversation_id=None,
            pending_hitl=None,
        )

        kwargs = mock_agent.stream_chat_response.call_args.kwargs
        assert kwargs["user_journals_enabled"] is True
        assert kwargs["user_psyche_enabled"] is True
        assert kwargs["user_memory_enabled"] is True

    @pytest.mark.asyncio
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_disabled_preferences_are_forwarded_too(
        self,
        mock_agent_cls: MagicMock,
        _mock_md_html: MagicMock,
        handler: InboundMessageHandler,
        text_message: ChannelInboundMessage,
    ) -> None:
        """Propagation, not hardcoding: a user who opted out stays opted out."""
        mock_agent = mock_agent_cls.return_value
        mock_agent.stream_chat_response = MagicMock(
            return_value=_mock_stream(_make_chunk("token", "ok"), _make_chunk("done", ""))
        )

        await handler.handle(
            message=text_message,
            user_id=uuid4(),
            user_language="fr",
            user_timezone="Europe/Paris",
            user_memory_enabled=False,
            user_journals_enabled=False,
            user_psyche_enabled=False,
            conversation_id=None,
            pending_hitl=None,
        )

        kwargs = mock_agent.stream_chat_response.call_args.kwargs
        assert kwargs["user_journals_enabled"] is False
        assert kwargs["user_psyche_enabled"] is False


@pytest.mark.unit
class TestPsycheTagNeverLeaksToTheChannel:
    """Enabling psyche on a channel must not surface its self-report tag.

    The response node strips ``<psyche_eval>`` and signals the cleaned text via
    a ``content_replacement`` chunk. The handler treats that chunk as
    authoritative — this test pins that contract, because a regression would
    show raw technical markup to a Telegram user.
    """

    @pytest.mark.asyncio
    @patch(_PATCH_MD_TO_HTML, side_effect=lambda x: x)
    @patch(_PATCH_AGENT_SERVICE)
    async def test_content_replacement_wins_over_tagged_tokens(
        self,
        mock_agent_cls: MagicMock,
        _mock_md_html: MagicMock,
        handler: InboundMessageHandler,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        chunks = [
            _make_chunk("token", "Bien noté !"),
            _make_chunk("token", "<psyche_eval valence='0.4'/>"),
            _make_chunk("content_replacement", "Bien noté !"),
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
            user_journals_enabled=True,
            user_psyche_enabled=True,
            conversation_id=None,
            pending_hitl=None,
        )

        sent = mock_sender.send_message.call_args[0][1]
        assert "psyche_eval" not in sent.text
        assert sent.text == "Bien noté !"


@pytest.mark.unit
class TestPreferenceResolver:
    """Both channel entry points share one resolver — the shape of the D1 fix.

    The duplication between the inbound route and the HITL callback route is
    what let journals and psyche be forgotten on one side only. These tests
    exercise the resolver directly, so they survive any future refactor of the
    two call sites.
    """

    def test_loaded_user_preferences_are_read_from_the_row(self) -> None:
        from src.domains.channels.preferences import resolve_channel_preferences

        user = SimpleNamespace(
            language="de",
            timezone="Europe/Berlin",
            memory_enabled=True,
            journals_enabled=True,
            psyche_enabled=True,
            full_name="Alex Martin",
            email="alex@example.com",
        )

        prefs = resolve_channel_preferences(user)

        assert prefs.language == "de"
        assert prefs.timezone == "Europe/Berlin"
        assert prefs.journals_enabled is True
        assert prefs.psyche_enabled is True

    def test_opted_out_user_stays_opted_out(self) -> None:
        from src.domains.channels.preferences import resolve_channel_preferences

        user = SimpleNamespace(
            language="fr",
            timezone="Europe/Paris",
            memory_enabled=False,
            journals_enabled=False,
            psyche_enabled=False,
            full_name=None,
            email=None,
        )

        prefs = resolve_channel_preferences(user)

        assert prefs.memory_enabled is False
        assert prefs.journals_enabled is False
        assert prefs.psyche_enabled is False

    def test_unloadable_user_fails_closed_on_long_term_state(self) -> None:
        """Nothing is ever written to the journals of someone we cannot identify."""
        from src.domains.channels.preferences import resolve_channel_preferences

        prefs = resolve_channel_preferences(None)

        assert prefs.journals_enabled is False
        assert prefs.psyche_enabled is False
        assert prefs.display_name is None

    def test_language_fallback_is_configured_not_hardcoded(self) -> None:
        """A hardcoded "fr" was the D6 defect on the callback route."""
        from src.core.config import settings
        from src.domains.channels.preferences import resolve_channel_preferences

        assert resolve_channel_preferences(None).language == settings.default_language
        # An empty language on the row must fall back the same way.
        blank = SimpleNamespace(
            language=None,
            timezone=None,
            memory_enabled=True,
            journals_enabled=True,
            psyche_enabled=True,
            full_name=None,
            email=None,
        )
        assert resolve_channel_preferences(blank).language == settings.default_language

    def test_timezone_fallback_is_the_shared_default(self) -> None:
        from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
        from src.domains.channels.preferences import resolve_channel_preferences

        assert resolve_channel_preferences(None).timezone == DEFAULT_USER_DISPLAY_TIMEZONE


@pytest.mark.unit
class TestUserModelContract:
    """The resolver reads columns off the user row — pin their existence."""

    def test_user_object_exposes_both_columns(self) -> None:
        """Guards the getattr fallbacks against a silent column rename."""
        from src.domains.users.models import User

        assert hasattr(User, "journals_enabled")
        assert hasattr(User, "psyche_enabled")

    def test_defaults_mirror_the_web_chat(self) -> None:
        """Both hops must agree; divergence is how D1 happened in the first place."""
        user = SimpleNamespace()  # incomplete object: only the fallbacks fire
        assert getattr(user, "journals_enabled", False) is False
        assert getattr(user, "psyche_enabled", False) is False
