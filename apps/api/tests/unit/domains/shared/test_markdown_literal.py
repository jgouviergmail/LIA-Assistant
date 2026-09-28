"""Text another person wrote, or a value a card shows, renders as itself (ADR-316, ADR-323).

A comment travelling with a shared image is quoted in the RECIPIENT's chat,
which renders Markdown with raw HTML allowed (sanitised) and images from any
``https:`` host (the CSP allows them). Rendered as written, a comment could
load a tracking image, hide a link behind friendly words, or draw markup that
reads like LIA's own. Quoted literally, it can only be read. A draft card's
values go further: they are drawn as the characters they hold, never as a
link the chat's tokenizer would cut. What the chat actually draws is pinned in
the browser (``data-literal-corpus.test.tsx`` renders this module's corpus
through the chat's own pipeline).

Numeric character references, not backslashes: the chat's math step reads an
escaped ``\\[x\\]`` as a LaTeX block (measured in the browser, the e2e spec
``chat-image-share`` pins the rendering).

The reader (``read_as_markdown``) reads those references back the way the chat
does, for the surfaces that render no Markdown.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pytest

from src.domains.agents.display.components.base import escape_html
from src.domains.shared.markdown_literal import (
    RESERVED_MARKERS,
    literal_quote,
    markdown_data_literal,
    markdown_literal,
    read_as_markdown,
)

pytestmark = pytest.mark.unit

#: Every character a Markdown or HTML reader could take for markup.
_PRINTABLE_ASCII = [chr(code) for code in range(0x20, 0x7F)]
BACKSLASH = chr(92)
#: Pinned by the browser too: every value, and what the chat must show.
CORPUS = Path(__file__).with_name("data_literal_corpus.json")


def _identity(text: str) -> str:
    return text


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
            (f"back{BACKSLASH}slash", "back&#92;slash"),
            ("&lt;b&gt;", "&#38;lt;b&#38;gt;"),
            ("$5 et $10", "&#36;5 et &#36;10"),
        ],
    )
    def test_what_would_become_markup_is_referenced(self, written: str, referenced: str) -> None:
        assert markdown_literal(written) == referenced

    def test_ordinary_prose_is_untouched(self) -> None:
        """Nothing may clutter plain words — a bare URL stays a link reading as itself."""
        prose = "Regarde ça, c'est pour Tom & Jerry ! 50 % réussi. *Vite* https://a.example/x_y"

        assert markdown_literal(prose) == prose


class TestTheDataVariant:
    def test_emphasis_and_strike_through_are_referenced(self) -> None:
        """« 2*3*4 » drew its 3 in italics; ``~~x~~`` struck its x through."""
        assert markdown_data_literal("2*3*4 ~~x~~") == "2&#42;3&#42;4 &#126;&#126;x&#126;&#126;"

    @pytest.mark.parametrize(
        ("value", "drawn"),
        [
            ("max_results: 10, page_token", "max_results: 10, page_token"),
            ("_x_ et __init__", "&#95;x&#95; et &#95;&#95;init&#95;&#95;"),
            ("fin_", "fin&#95;"),
            ("a__b", "a&#95;&#95;b"),
            ("é_中", "é_中"),
        ],
        ids=["between_words", "delimiters", "trailing", "a_run", "non_latin"],
    )
    def test_an_underscore_is_referenced_only_where_it_could_delimit(
        self, value: str, drawn: str
    ) -> None:
        """CommonMark never opens ``_`` emphasis inside a word, so an identifier
        stays as typed — and a model reading the card reads it as typed too."""
        assert markdown_data_literal(value) == drawn

    @pytest.mark.parametrize(
        ("value", "drawn"),
        [
            ("https://a.example/x", "https&#58;//a.example/x"),
            ("HTTP://A.EXAMPLE", "HTTP&#58;//A.EXAMPLE"),
            ("www.a.example", "www&#46;a.example"),
            ("WWW.A.EXAMPLE", "WWW&#46;A.EXAMPLE"),
            ("jean_dupont@example.com", "jean_dupont&#64;example.com"),
            ("Objet : https: sans barres", "Objet : https: sans barres"),
            ("a.b.c et v2.1", "a.b.c et v2.1"),
        ],
    )
    def test_the_chat_s_tokenizer_never_links_a_value(self, value: str, drawn: str) -> None:
        """The tokenizer links on the RAW source: a reference inside or right
        after a URL was swallowed into the link or cut it (review 14:
        ``jean&#95;dupont@example.com`` linked to ``dupont@example.com``).
        Its three triggers are referenced; what the chat still links, it links
        on the decoded text, so its text is always its address."""
        assert markdown_data_literal(value) == drawn

    @pytest.mark.parametrize("char", _PRINTABLE_ASCII, ids=lambda c: f"U+{ord(c):04X}")
    def test_a_lone_character_is_referenced_exactly_when_it_could_act(self, char: str) -> None:
        drawn = markdown_data_literal(char)

        acting = set(f"{BACKSLASH}`[]<>$*~@_")
        assert (drawn == f"&#{ord(char)};") == (char in acting)
        assert drawn in (char, f"&#{ord(char)};")

    def test_an_ampersand_is_referenced_only_before_a_reference(self) -> None:
        assert markdown_data_literal("Tom & Jerry &amp; &#233; &copy=2") == (
            "Tom & Jerry &#38;amp; &#38;#233; &copy=2"
        )


class TestTheCorpus:
    """The values the browser renders through the chat's own pipeline."""

    @pytest.mark.parametrize(
        "case", json.loads(CORPUS.read_text(encoding="utf-8"))["cases"], ids=lambda c: c["id"]
    )
    def test_each_value_is_drawn_as_the_corpus_says(self, case: dict[str, str]) -> None:
        assert markdown_data_literal(case["value"]) == case["drawn"]

    @pytest.mark.parametrize(
        "case", json.loads(CORPUS.read_text(encoding="utf-8"))["html"], ids=lambda c: c["id"]
    )
    def test_each_html_card_value_is_drawn_as_the_corpus_says(self, case: dict[str, str]) -> None:
        """The same promise for the chat's HTML cards (``escape_html``)."""
        assert escape_html(case["value"]) == case["drawn"]

    def test_the_corpus_holds_every_character_the_encoder_references(self) -> None:
        """A character added to the encoder and not to the corpus would never
        be proven to render as itself in the chat."""
        values = "".join(case["value"] for case in json.loads(CORPUS.read_text("utf-8"))["cases"])
        referenced = {char for char in _PRINTABLE_ASCII if markdown_data_literal(char) != char} | {
            ":",
            ".",
        }

        assert referenced <= set(values)


class TestTheReader:
    @pytest.mark.parametrize(
        ("text", "read"),
        [
            ("tape &#233; ici", "tape é ici"),
            ("&eacute;&#x2F;&amp;lt;", "é/&lt;"),
            ("&#0; &#xD800; &#1114112;", "� � �"),
            ("&unknownname; &copy=2 &", "&unknownname; &copy=2 &"),
            ("Réunion &#60;lundi&#62; &#91;v2&#93;", "Réunion <lundi> [v2]"),
        ],
        ids=["numeric", "named_and_single_pass", "invalid", "not_references", "card_values"],
    )
    def test_references_are_read_as_the_chat_reads_them(self, text: str, read: str) -> None:
        assert read_as_markdown(text, _identity) == read

    def test_a_reference_in_code_stays_as_typed(self) -> None:
        """The chat shows ``&#91;`` inside a code span — the ticket read « [ »
        and Telegram drew it as « [ » (review 14)."""
        text = "tape `&#91;` et\n```\n&#42;x&#42; &lt;\n```\npuis &#42;"

        assert read_as_markdown(text, _identity) == (
            "tape `&#91;` et\n```\n&#42;x&#42; &lt;\n```\npuis *"
        )

    def test_the_flattener_never_meets_what_the_references_spell(self) -> None:
        """Decoded first, « &#60;lundi&#62; » became a tag the HTML stripper
        removed, and « &#42;&#42;x&#42;&#42; » an emphasis a Markdown one dropped."""

        def flatten(text: str) -> str:
            assert "&" not in text and "<lundi>" not in text and "**" not in text
            return re.sub(r"<[^>]+>", "", text).replace("**", "")

        assert read_as_markdown(
            "<p>Réunion &#60;lundi&#62; &#42;&#42;x&#42;&#42;</p>", flatten
        ) == ("Réunion <lundi> **x**")

    def test_a_bare_ampersand_never_reaches_an_html_decoder(self) -> None:
        """HTML5 decodes « &copy=2 » as « ©=2 »; the chat reads Markdown, which does not."""
        assert read_as_markdown("<p>x</p> ?id=7&copy=2&not=1", html.unescape) == (
            "<p>x</p> ?id=7&copy=2&not=1"
        )

    def test_a_bare_url_keeps_its_marks(self) -> None:
        def flatten(text: str) -> str:
            return re.sub(r"[*_~]", "", text)

        assert read_as_markdown("voir https://a.example/x_y*z* et *gras*", flatten) == (
            "voir https://a.example/x_y*z* et gras"
        )

    def test_what_is_kept_is_written_back_by_the_surface(self) -> None:
        assert read_as_markdown("a &#60;b&#62; & c", _identity, restore=html.escape) == (
            "a &lt;b&gt; &amp; c"
        )

    @pytest.mark.parametrize(
        "text",
        [
            "raw \U000f003c b \U000f003e and \U000f0080 esc \U000f0100",
            "&#983100; &#983168;",
            "".join(RESERVED_MARKERS[:3]),
        ],
        ids=["raw_reserved", "referenced_reserved", "markers"],
    )
    def test_the_reading_is_one_to_one(self, text: str) -> None:
        """A raw character of the reserved block came back as an ASCII mark —
        « Objet 󰀼b󰀾 » read « Objet <b> » (review 14)."""
        expected = text.replace("&#983100;", "\U000f003c").replace("&#983168;", "\U000f0080")

        assert read_as_markdown(text, _identity) == expected

    def test_the_flattener_is_handed_no_reserved_marker(self) -> None:
        seen: list[str] = []

        def flatten(text: str) -> str:
            seen.append(text)
            return text

        read_as_markdown("".join(RESERVED_MARKERS) + " &#983169;", flatten)

        assert not set(seen[0]) & set(RESERVED_MARKERS)


class TestLiteralQuote:
    def test_every_line_is_quoted_and_blank_lines_keep_the_quote_open(self) -> None:
        assert literal_quote("first\n\nsecond <b>") == "> first\n>\n> second &#60;b&#62;"

    def test_surrounding_blank_lines_are_dropped(self) -> None:
        assert literal_quote("\n\n  hello  \n\n") == "> hello"

    def test_a_line_cannot_open_a_nested_quote(self) -> None:
        assert literal_quote("> not a quote") == "> &#62; not a quote"
