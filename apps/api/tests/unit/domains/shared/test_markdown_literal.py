"""Text another person wrote renders as itself in a chat bubble (ADR-316).

A comment travelling with a shared image is quoted in the RECIPIENT's chat,
which renders Markdown with raw HTML allowed (sanitised) and images from any
``https:`` host (the CSP allows them). Rendered as written, a comment could
load a tracking image, hide a link behind friendly words, or draw markup that
reads like LIA's own. Quoted literally, it can only be read.

Numeric character references, not backslashes: the chat's math step reads an
escaped ``\\[x\\]`` as a LaTeX block (measured in the browser, the e2e spec
``chat-image-share`` pins the rendering).
"""

from __future__ import annotations

import pytest

from src.domains.shared.markdown_literal import literal_quote, markdown_literal

pytestmark = pytest.mark.unit


class TestMarkdownLiteral:
    @pytest.mark.parametrize(
        ("written", "referenced"),
        [
            (
                "![pixel](https://tracker.example/p.png)",
                "!&#91;pixel&#93;(https://tracker.example/p.png)",
            ),
            ("[click here](https://phish.example)", "&#91;click here&#93;(https://phish.example)"),
            ("<img src=x onerror=alert(1)>", "&#60;img src=x onerror=alert(1)&#62;"),
            ("`code`", "&#96;code&#96;"),
            ("back\\slash", "back&#92;slash"),
            ("&lt;b&gt;", "&#38;lt;b&#38;gt;"),
        ],
    )
    def test_what_would_become_markup_is_referenced(self, written: str, referenced: str) -> None:
        assert markdown_literal(written) == referenced

    def test_ordinary_prose_is_untouched(self) -> None:
        """Pushes and channels show the raw text: nothing may clutter plain words."""
        prose = "Regarde ça, c'est pour Tom & Jerry ! 50 % réussi. *Vite*"

        assert markdown_literal(prose) == prose


class TestLiteralQuote:
    def test_every_line_is_quoted_and_blank_lines_keep_the_quote_open(self) -> None:
        assert literal_quote("first\n\nsecond <b>") == "> first\n>\n> second &#60;b&#62;"

    def test_surrounding_blank_lines_are_dropped(self) -> None:
        assert literal_quote("\n\n  hello  \n\n") == "> hello"

    def test_a_line_cannot_open_a_nested_quote(self) -> None:
        assert literal_quote("> not a quote") == "> &#62; not a quote"
