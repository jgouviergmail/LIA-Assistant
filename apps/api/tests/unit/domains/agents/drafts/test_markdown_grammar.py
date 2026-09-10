"""The one Markdown vocabulary every draft-facing surface speaks (ADR-276 lot 13).

Two surfaces build rows: the confirmation preview (what a person is asked to
approve) and the execution result (what happened once they did). They used to
speak two vocabularies — the preview Markdown since lot 13, the result still
HTML ``<br/>`` — so the same email read as a clean list before confirmation and
as a stack of blank lines after it.

These tests pin the grammar itself, independently of either caller: the shape
of a row, what a non-string value becomes, and the fact that the punctuation
between a label and its value travels with the LANGUAGE rather than being a
``": "`` literal.
"""

from __future__ import annotations

import pytest

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.drafts.markdown_grammar import (
    labelled_block,
    labelled_row,
    plain_row,
    readable,
)

pytestmark = pytest.mark.unit


class TestReadable:
    def test_a_string_is_itself(self) -> None:
        assert readable("paul@example.com") == "paul@example.com"

    @pytest.mark.parametrize(
        "value",
        [
            ["a@example.com", "b@example.com"],
            ("a@example.com", "b@example.com"),
        ],
        ids=["list", "tuple"],
    )
    def test_a_sequence_is_joined_never_python_spelled(self, value: object) -> None:
        """A recipient list must never reach a card as ``['a@…']``."""
        assert readable(value) == "a@example.com, b@example.com"

    def test_a_set_is_joined_too(self) -> None:
        assert readable({"solo@example.com"}) == "solo@example.com"

    def test_a_nested_sequence_is_flattened_by_recursion(self) -> None:
        assert readable([["a"], ["b", "c"]]) == "a, b, c"

    def test_anything_else_is_stringified(self) -> None:
        assert readable(42) == "42"
        assert readable(None) == "None"

    def test_a_dict_is_stringified_rather_than_joined(self) -> None:
        """A mapping is not a sequence of values here: joining its KEYS would
        state something the content never said."""
        assert readable({"name": "x"}) == "{'name': 'x'}"


class TestLabelledRow:
    def test_a_row_is_a_markdown_list_item_with_a_bold_label(self) -> None:
        assert labelled_row("Objet", " : ", "Bonjour") == "- **Objet** : Bonjour"

    def test_a_row_never_emits_a_hard_break(self) -> None:
        assert "<br" not in labelled_row("Objet", " : ", "Bonjour")

    def test_the_value_goes_through_readable(self) -> None:
        assert labelled_row("À", ": ", ["a", "b"]) == "- **À**: a, b"


class TestPlainRow:
    def test_a_note_is_a_list_item_with_no_label(self) -> None:
        assert plain_row("Aucune pièce jointe") == "- Aucune pièce jointe"


class TestLabelledBlock:
    def test_a_text_leaves_the_list_and_keeps_its_paragraphs(self) -> None:
        block = labelled_block("Message", "Bonjour,\n\nÀ demain.")
        assert block == "\n**Message**\n\nBonjour,\n\nÀ demain.\n"


class TestSeparatorTravelsWithTheLanguage:
    """A ``": "`` literal published French punctuation in six languages."""

    @pytest.mark.parametrize(
        "language,expected",
        [
            ("fr", " : "),
            ("en", ": "),
            ("es", ": "),
            ("de", ": "),
            ("it", ": "),
            ("zh-CN", "："),
        ],
    )
    def test_every_language_declares_its_own_separator(self, language: str, expected: str) -> None:
        labels = get_draft_preview_labels(language)
        assert labels["separator"] == expected

    def test_french_puts_an_unbreakable_space_before_the_colon(self) -> None:
        """Typography, not decoration: a French colon is preceded by a space
        the line must never break on."""
        separator = get_draft_preview_labels("fr")["separator"]
        assert separator[0] in (" ", " ")

    def test_chinese_uses_its_own_full_width_colon_with_no_space(self) -> None:
        separator = get_draft_preview_labels("zh-CN")["separator"]
        assert separator == "："
        assert " " not in separator
