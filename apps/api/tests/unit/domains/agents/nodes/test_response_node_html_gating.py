"""Unit tests for the HTML-directive gating in ``response_node``.

Regression guard for the "TTS reads HTML aloud" bug (conversation + HTML
display mode): the rich HTML response directive must only be injected for
tool/data turns (router ``route_to == "planner"``, i.e. router intention
``"action"``), never for conversational turns whose reply is streamed
verbatim to the TTS engine via the progressive chat path.

The gate keys on ``route_to`` because that is, by definition, the exact
source the router derives its ``intention`` from
(``"action" if route_to == "planner" else "conversation"``) — the same
signal the voice path uses to start progressive TTS. Keying on the identical
source guarantees the display gate and the voice trigger can never desync.
"""

import pytest

from src.core.constants import (
    RESPONSE_DISPLAY_MODE_CARDS,
    RESPONSE_DISPLAY_MODE_HTML,
    RESPONSE_DISPLAY_MODE_MARKDOWN,
)
from src.domains.agents.nodes.response_node import _should_inject_html_directive


@pytest.mark.unit
class TestShouldInjectHtmlDirective:
    """The directive is injected only for HTML mode AND a planner-routed turn."""

    def test_html_mode_action_turn_injects(self) -> None:
        assert _should_inject_html_directive(RESPONSE_DISPLAY_MODE_HTML, "planner") is True

    def test_html_mode_conversation_turn_suppressed(self) -> None:
        # route_to != "planner" => router intention == "conversation" => voice
        # streams the reply verbatim; HTML must NOT be emitted.
        assert _should_inject_html_directive(RESPONSE_DISPLAY_MODE_HTML, "response") is False

    def test_html_mode_missing_route_suppressed(self) -> None:
        # Defensive: missing/fallback query intelligence => treat as conversation
        # (safe default — never feed HTML to TTS).
        assert _should_inject_html_directive(RESPONSE_DISPLAY_MODE_HTML, None) is False

    def test_cards_mode_never_injects(self) -> None:
        assert _should_inject_html_directive(RESPONSE_DISPLAY_MODE_CARDS, "planner") is False

    def test_markdown_mode_never_injects(self) -> None:
        assert _should_inject_html_directive(RESPONSE_DISPLAY_MODE_MARKDOWN, "planner") is False

    def test_cards_mode_conversation_never_injects(self) -> None:
        assert _should_inject_html_directive(RESPONSE_DISPLAY_MODE_CARDS, "response") is False
