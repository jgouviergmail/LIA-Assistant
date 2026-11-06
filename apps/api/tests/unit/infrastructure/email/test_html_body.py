"""What a message written with formatting may hold (ADR-369, lot 7.4).

The page's editor writes HTML, and whatever reaches the server is a stranger's. Nothing is
filtered out of it: what leaves is REBUILT from an allowlist, so what nobody thought of never
passes. The words always survive what carried them.
"""

from __future__ import annotations

import pytest

from src.infrastructure.email.html_body import clean_message_html

pytestmark = pytest.mark.unit


class TestWhatStays:
    @pytest.mark.parametrize(
        "html",
        [
            "<b>bold</b>",
            "<strong>bold</strong>",
            "<i>it</i>",
            "<em>it</em>",
            "<u>under</u>",
            "<s>gone</s>",
            "<p>para</p>",
            "<div>line</div>",
            "<ul><li>one</li></ul>",
            "<ol><li>one</li></ol>",
            "<blockquote>said</blockquote>",
        ],
    )
    def test_the_marks_the_editor_writes(self, html: str) -> None:
        assert clean_message_html(html) == html

    def test_a_line_break_is_written_once(self) -> None:
        assert clean_message_html("a<br>b<br/>c") == "a<br>b<br>c"

    @pytest.mark.parametrize(
        "href",
        ["https://example.org/a?b=1&amp;c=2", "http://example.org", "mailto:ana@example.org"],
    )
    def test_a_link_people_can_follow(self, href: str) -> None:
        assert clean_message_html(f'<a href="{href}">x</a>') == f'<a href="{href}">x</a>'

    def test_accents_and_entities_read_the_same(self) -> None:
        assert clean_message_html("Été &amp; caf&eacute; &lt;x&gt;") == "Été &amp; café &lt;x&gt;"


class TestWhatGoes:
    @pytest.mark.parametrize(
        ("html", "kept"),
        [
            ("<script>alert(1)</script>after", "after"),
            ("<style>p{color:red}</style>after", "after"),
            ("<iframe src='https://x'>in</iframe>after", "after"),
            ("<object data='x'>in</object>after", "after"),
            ("<svg><script>alert(1)</script></svg>after", "after"),
            ("<svg><text>drawn</text></svg>after", "after"),
            ("<noscript><img src=x></noscript>after", "after"),
            ("<template><b>x</b></template>after", "after"),
        ],
    )
    def test_what_holds_code_goes_with_everything_in_it(self, html: str, kept: str) -> None:
        assert clean_message_html(html) == kept

    @pytest.mark.parametrize(
        ("html", "kept"),
        [
            ("<h1>title</h1>", "title"),
            ("<table><tr><td>cell</td></tr></table>", "cell"),
            ("<font color=red>word</font>", "word"),
            ("<span>word</span>", "word"),
            ("<custom-tag>word</custom-tag>", "word"),
        ],
    )
    def test_an_unknown_mark_leaves_its_words(self, html: str, kept: str) -> None:
        assert clean_message_html(html) == kept

    def test_no_attribute_survives_but_a_link_s(self) -> None:
        html = '<p onclick="x()" style="color:red" class="c" id="i">a</p>'

        assert clean_message_html(html) == "<p>a</p>"

    @pytest.mark.parametrize(
        "href",
        [
            "javascript:alert(1)",
            "JaVaScRiPt:alert(1)",
            " javascript:alert(1)",
            "java\tscript:alert(1)",
            "java\nscript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "vbscript:x",
            "file:///etc/passwd",
            "//example.org/x",
            "/relative",
            "#top",
            "http://[not-an-address",
        ],
    )
    def test_a_link_nobody_should_follow_keeps_only_its_words(self, href: str) -> None:
        assert clean_message_html(f'<a href="{href}">x</a>') == "x"

    def test_an_image_is_not_something_the_editor_writes(self) -> None:
        assert clean_message_html('<img src="https://tracker/x.png">after') == "after"

    def test_a_comment_goes(self) -> None:
        assert clean_message_html("a<!-- b -->c") == "ac"

    def test_a_tag_written_in_text_stays_text(self) -> None:
        assert clean_message_html("&lt;script&gt;x") == "&lt;script&gt;x"

    def test_a_quote_cannot_close_an_attribute(self) -> None:
        html = '<a href="https://example.org/&quot;onclick=&quot;x">y</a>'

        assert clean_message_html(html) == (
            '<a href="https://example.org/&quot;onclick=&quot;x">y</a>'
        )


class TestItsShape:
    def test_what_is_left_open_is_closed(self) -> None:
        assert clean_message_html("<b>a<i>b") == "<b>a<i>b</i></b>"

    def test_a_closing_mark_nothing_opened_is_dropped(self) -> None:
        assert clean_message_html("a</b>c") == "ac"

    def test_a_stray_closing_mark_closes_nothing_else(self) -> None:
        assert clean_message_html("<b>a</i>c</b>") == "<b>ac</b>"

    def test_marks_closed_out_of_order_are_closed_in_order(self) -> None:
        assert clean_message_html("<b><i>a</b>c</i>") == "<b><i>a</i></b>c"

    def test_nothing_stays_nothing(self) -> None:
        assert clean_message_html("") == ""
