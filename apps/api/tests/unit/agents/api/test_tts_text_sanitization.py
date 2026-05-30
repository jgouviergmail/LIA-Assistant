"""Unit tests for the TTS text safety net in ``agents.api.service``.

Defense-in-depth (vector B): any path that feeds the TTS engine the raw
assistant response (reference turns, post-LLM data cards, sync voice
fallbacks) must strip HTML to speakable text — WITHOUT mangling plain prose
that merely contains angle brackets (e.g. ``"x < 5 and y > 3"``) or Markdown
symbols.

The guard exists because :func:`html_to_text` ends with
``re.sub(r"<[^>]+>", "", text)``, which would happily delete ``"< 5 and y >"``
from ``"x < 5 and y > 3"``. So we only run the stripper when the content is
*actually* HTML, detected via recognised element tags or the LLM's
``lia-response`` / ``<style>`` wrappers.
"""

import pytest

from src.domains.agents.api.service import _looks_like_html, _sanitize_text_for_tts


@pytest.mark.unit
class TestLooksLikeHtml:
    def test_detects_lia_response_wrapper(self) -> None:
        assert _looks_like_html('<div class="lia-response"><p>Hi</p></div>') is True

    def test_detects_style_block(self) -> None:
        assert _looks_like_html("<style>.x{color:red}</style>Hello") is True

    def test_detects_simple_tag(self) -> None:
        assert _looks_like_html("<p>hello</p>") is True

    def test_plain_comparison_not_html(self) -> None:
        # The critical guard: prose with bare angle brackets is NOT HTML.
        assert _looks_like_html("x < 5 and y > 3") is False

    def test_code_snippet_not_html(self) -> None:
        assert _looks_like_html("if a < b and b > c: return True") is False

    def test_markdown_not_html(self) -> None:
        assert _looks_like_html("**bold** and # title and - item") is False

    def test_empty_not_html(self) -> None:
        assert _looks_like_html("") is False

    def test_lia_response_mention_in_prose_not_html(self) -> None:
        # Detection relies on element tags only — prose that merely names the
        # CSS class must NOT be treated as HTML (no tags present).
        assert _looks_like_html("The lia-response layout improved a lot") is False


@pytest.mark.unit
class TestSanitizeTextForTts:
    def test_strips_html_response_blob(self) -> None:
        html = (
            '<div class="lia-response"><style>.lia-response{color:#000}</style>'
            "<p>Bonjour, comment vas-tu ?</p></div>"
        )
        out = _sanitize_text_for_tts(html)
        assert "<" not in out
        assert "color" not in out  # CSS from the <style> block is removed entirely
        assert "Bonjour, comment vas-tu ?" in out

    def test_preserves_angle_bracket_prose(self) -> None:
        # Regression guard: must NOT delete "< 5 and y >".
        text = "x < 5 and y > 3 donc c'est bon"
        assert _sanitize_text_for_tts(text) == text

    def test_preserves_markdown(self) -> None:
        text = "**Salut** ! Voici # un titre et - une liste"
        assert _sanitize_text_for_tts(text) == text

    def test_strips_simple_tag(self) -> None:
        assert _sanitize_text_for_tts("<div>hello</div>").strip() == "hello"

    def test_empty_is_noop(self) -> None:
        assert _sanitize_text_for_tts("") == ""

    def test_preserves_lia_response_mention_with_angle_brackets(self) -> None:
        # Regression guard for the removed substring check: prose that names
        # "lia-response" AND contains bare angle brackets must be left intact.
        text = "the lia-response system keeps x < 5 and y > 3 readable"
        assert _sanitize_text_for_tts(text) == text
