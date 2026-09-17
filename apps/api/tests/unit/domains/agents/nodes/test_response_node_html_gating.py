"""Unit tests for the HTML-directive gating in ``response_node``.

The rich HTML response directive is worth its tokens on every turn of an
account that chose the ``html`` display mode: the frontend renders the
``lia-response`` document and a Markdown reply through the same pipeline.
The one reader that cannot take markup is the voice — on a conversational
turn (router ``route_to != "planner"``) the reply is streamed verbatim to the
TTS engine through the progressive chat path, so a tag would be spoken aloud.

The gate therefore suppresses the directive only where that voice actually
listens: a conversational turn of an account whose voice preference is on.
It keys on the SAME two signals the voice path starts from — the router's
``route_to`` (its ``intention`` is derived from it) and the account's
``voice_enabled`` flag — so the display gate and the voice trigger cannot
desync.
"""

import pytest

from src.core.constants import (
    RESPONSE_DISPLAY_MODE_CARDS,
    RESPONSE_DISPLAY_MODE_HTML,
    RESPONSE_DISPLAY_MODE_MARKDOWN,
)
from src.domains.agents.nodes.response_node import _should_inject_html_directive

pytestmark = pytest.mark.unit


class TestActionTurns:
    """A planner-routed turn is never read aloud verbatim: HTML whenever the mode asks."""

    @pytest.mark.parametrize("voice_enabled", [True, False])
    def test_html_mode_injects_whatever_the_voice_preference(self, voice_enabled: bool) -> None:
        assert (
            _should_inject_html_directive(RESPONSE_DISPLAY_MODE_HTML, "planner", voice_enabled)
            is True
        )


class TestConversationalTurns:
    """A conversational reply is read verbatim by the voice: HTML only when none listens."""

    def test_html_mode_with_the_voice_off_injects(self) -> None:
        assert _should_inject_html_directive(RESPONSE_DISPLAY_MODE_HTML, "response", False) is True

    def test_html_mode_with_the_voice_on_is_suppressed(self) -> None:
        assert _should_inject_html_directive(RESPONSE_DISPLAY_MODE_HTML, "response", True) is False

    def test_a_missing_route_reads_as_conversational(self) -> None:
        # A fallback or missing query intelligence is a conversational turn:
        # with the voice on, nothing may reach the TTS as markup.
        assert _should_inject_html_directive(RESPONSE_DISPLAY_MODE_HTML, None, True) is False
        assert _should_inject_html_directive(RESPONSE_DISPLAY_MODE_HTML, None, False) is True


class TestOtherDisplayModes:
    """Only the ``html`` mode ever asks for the directive."""

    @pytest.mark.parametrize(
        "display_mode", [RESPONSE_DISPLAY_MODE_CARDS, RESPONSE_DISPLAY_MODE_MARKDOWN, None]
    )
    @pytest.mark.parametrize("route_to", ["planner", "response", None])
    @pytest.mark.parametrize("voice_enabled", [True, False])
    def test_never_injects(
        self, display_mode: str | None, route_to: str | None, voice_enabled: bool
    ) -> None:
        assert _should_inject_html_directive(display_mode, route_to, voice_enabled) is False
