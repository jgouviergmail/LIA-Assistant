"""Unit tests for ``coerce_content_to_text`` (Gemini 3.x list-content normalization)."""

import pytest

from src.infrastructure.llm.message_text import coerce_content_to_text


class TestCoerceMessageText:
    """Validate plain-text normalization across every content shape."""

    def test_str_passthrough(self) -> None:
        """A plain string (non-Gemini-3.x providers) is returned unchanged."""
        assert coerce_content_to_text("hello world") == "hello world"

    def test_empty_str_passthrough(self) -> None:
        """An empty string stays an empty string."""
        assert coerce_content_to_text("") == ""

    def test_none_returns_empty_str(self) -> None:
        """``None`` content normalizes to an empty string, never crashes."""
        assert coerce_content_to_text(None) == ""

    def test_gemini3_text_blocks_concatenated(self) -> None:
        """Gemini 3.x list of text blocks is flattened to concatenated text."""
        content = [
            {"type": "text", "text": "hel", "index": 0},
            {"type": "text", "text": "lo", "index": 1},
        ]
        assert coerce_content_to_text(content) == "hello"

    def test_single_text_block(self) -> None:
        """A single-block list (typical full Gemini 3.x answer) yields its text."""
        content = [{"type": "text", "text": "Voici tes deux prochains rdv.", "index": 0}]
        assert coerce_content_to_text(content) == "Voici tes deux prochains rdv."

    def test_non_text_blocks_ignored(self) -> None:
        """Reasoning / thought-signature / tool-use blocks are dropped."""
        content = [
            {"type": "thinking", "thinking": "internal reasoning"},
            {"type": "text", "text": "answer"},
            {"type": "tool_use", "name": "search"},
        ]
        assert coerce_content_to_text(content) == "answer"

    def test_block_without_type_defaults_to_text(self) -> None:
        """A block carrying only a ``text`` key is treated as text."""
        assert coerce_content_to_text([{"text": "raw"}]) == "raw"

    def test_raw_string_blocks(self) -> None:
        """A list of bare strings is concatenated."""
        assert coerce_content_to_text(["a", "b", "c"]) == "abc"

    def test_empty_list_returns_empty_str(self) -> None:
        """An empty list (e.g. pure reasoning chunk) yields an empty string."""
        assert coerce_content_to_text([]) == ""

    def test_malformed_block_does_not_crash(self) -> None:
        """A text block whose ``text`` is not a string is skipped, not crashed."""
        content = [{"type": "text", "text": None}, {"type": "text", "text": "ok"}]
        assert coerce_content_to_text(content) == "ok"

    @pytest.mark.parametrize("value", [42, 3.14, True])
    def test_unexpected_scalar_falls_back_to_str(self, value: object) -> None:
        """A non-str/list/None value falls back to ``str()`` rather than raising."""
        assert coerce_content_to_text(value) == str(value)
