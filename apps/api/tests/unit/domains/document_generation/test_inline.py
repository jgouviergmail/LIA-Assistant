"""Inline emphasis: ONE span list for docx/pptx/pdf; orphans stay literal (ADR-274).

The prompt allows ``**bold**`` and ``*italic*``; models also produce
``_italic_``, backticked code and markdown links. Every rich renderer consumes
the same spans, so an emphasis renders identically in the three — and a stray
asterisk in a price list survives untouched.
"""

import pytest

from src.domains.document_generation.inline import Span, parse_inline, strip_inline

pytestmark = [pytest.mark.unit]


class TestEmphasisBecomesSpans:
    def test_bold_italic_code_and_plain_text(self) -> None:
        assert parse_inline("a **b** c *d* e `f` g") == [
            Span("a "),
            Span("b", bold=True),
            Span(" c "),
            Span("d", italic=True),
            Span(" e "),
            Span("f", code=True),
            Span(" g"),
        ]

    def test_bold_italic_combined_and_underscore_italic(self) -> None:
        assert parse_inline("***x*** _y_") == [
            Span("x", bold=True, italic=True),
            Span(" "),
            Span("y", italic=True),
        ]

    def test_double_underscore_is_bold_not_an_italic_full_of_underscores(self) -> None:
        """The other markdown spelling of bold: repaired, never shown raw."""
        assert parse_inline("__y__") == [Span("y", bold=True)]
        assert parse_inline("___z___") == [Span("z", bold=True, italic=True)]

    def test_emphasis_at_both_ends(self) -> None:
        assert parse_inline("**all bold**") == [Span("all bold", bold=True)]
        assert parse_inline("**a** and **b**") == [
            Span("a", bold=True),
            Span(" and "),
            Span("b", bold=True),
        ]


class TestWhatMustStayLiteral:
    @pytest.mark.parametrize(
        "text",
        [
            "2 * 3 * 4",  # arithmetic
            "snake_case_name",  # an identifier, not italics
            "a_b_c",
            "**unclosed",
            "price: 5*",
            "3 * 4 = 12",
            "",
        ],
    )
    def test_orphan_and_intra_word_markers_are_not_emphasis(self, text: str) -> None:
        assert parse_inline(text) == ([Span(text)] if text else [])

    def test_escaped_markers_survive_as_characters(self) -> None:
        assert parse_inline(r"a \*literal\* **粗体**") == [
            Span("a *literal* "),
            Span("粗体", bold=True),
        ]

    def test_a_lone_asterisk_between_words_is_kept(self) -> None:
        assert strip_inline("cost * quantity") == "cost * quantity"


class TestLinksAndPlainText:
    def test_a_link_becomes_text_and_its_url(self) -> None:
        """A document is read on paper too: the address must survive visibly."""
        assert parse_inline("see [LIA](https://example.org/x) now") == [
            Span("see LIA (https://example.org/x) now")
        ]

    def test_strip_returns_the_words_without_the_markers(self) -> None:
        assert strip_inline("**b** and *i* and `c`") == "b and i and c"

    def test_cjk_text_is_untouched(self) -> None:
        assert parse_inline("这是一个中文段落。") == [Span("这是一个中文段落。")]
