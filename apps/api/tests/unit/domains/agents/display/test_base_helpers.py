"""Unit tests for the shared rendering helpers of the card layer.

``components/base.py`` is the library every card builds on: escaping, URL
safety, phone/date/duration/size formatting, HTML flattening. A regression in
any of them is invisible — the card still renders, it just renders something
wrong (or, for ``safe_url``, something dangerous).

``safe_url`` gets the most attention: it is the ONLY thing standing between a
payload URL — from a web-search result, a place website, a Drive link, an
arbitrary MCP server — and an ``href`` the user can click. HTML escaping does
not help there: ``javascript:alert(1)`` contains no character
``html.escape`` touches.
"""

from datetime import UTC, datetime

import pytest

from src.domains.agents.display.components.base import (
    build_directions_url,
    build_place_url,
    compact_html,
    escape_html,
    format_duration,
    format_email_body,
    format_file_size,
    format_phone,
    html_to_text,
    markdown_links_to_html,
    phone_for_tel,
    render_chip_stars,
    safe_css_color,
    safe_url,
    truncate,
)

pytestmark = pytest.mark.unit


# ============================================================================
# URL SAFETY
# ============================================================================


class TestSafeUrl:
    """Scheme allow-list for every href/src the card layer emits."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com/page?a=1",
            "http://example.com",
            "mailto:jane@example.com",
            "tel:+33123456789",
            "/api/v1/connectors/gmail/attachment/1/2",
        ],
    )
    def test_allowed_schemes_pass_through(self, url: str) -> None:
        assert safe_url(url) == escape_html(url)

    @pytest.mark.parametrize(
        "url",
        [
            "javascript:alert(1)",
            "JavaScript:alert(1)",
            "  javascript:alert(1)",
            "java\tscript:alert(1)",
            "java\nscript:alert(1)",
            "\x00javascript:alert(1)",
            "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
            "vbscript:msgbox(1)",
            "file:///etc/passwd",
        ],
    )
    def test_dangerous_schemes_are_dropped(self, url: str) -> None:
        """Browsers ignore control characters before resolving the scheme."""
        assert safe_url(url) == ""

    def test_protocol_relative_urls_are_dropped(self) -> None:
        """``//evil.example`` would inherit the app origin's scheme."""
        assert safe_url("//evil.example/x") == ""

    def test_query_string_is_escaped(self) -> None:
        assert safe_url("https://example.com/?a=1&b=2") == "https://example.com/?a=1&amp;b=2"

    def test_quote_in_url_cannot_break_out_of_the_attribute(self) -> None:
        result = safe_url('https://example.com/" onerror="alert(1)')
        assert '"' not in result
        assert "&quot;" in result

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_empty_values_produce_no_href(self, value: str | None) -> None:
        assert safe_url(value) == ""


class TestSafeCssColor:
    """The gate for any external color written into an inline ``style`` attr."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("#FF0000", "#FF0000"),
            ("#abc", "#abc"),
            ("#12345678", "#12345678"),
            ("00aa00", "#00aa00"),
            ("FFF", "#FFF"),
            ("red", "red"),
            ("dodgerblue", "dodgerblue"),
            ("  #FF0000  ", "#FF0000"),
        ],
    )
    def test_valid_colors_pass_through(self, raw: str, expected: str) -> None:
        assert safe_css_color(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            '#fff" onmouseover="alert(1)',
            "#fff; background: url(javascript:alert(1))",
            "red; color: expression(alert(1))",
            "url(x)",
            "#12345",  # wrong hex length
            "#gggggg",  # non-hex digits
            "rgb(1,2,3)",  # parens not allowed
            "12 34",
        ],
    )
    def test_hostile_or_malformed_colors_are_rejected(self, raw: str) -> None:
        assert safe_css_color(raw) == ""

    def test_default_is_returned_for_a_rejected_color(self) -> None:
        assert safe_css_color('#fff"', default="#FFFFFF") == "#FFFFFF"

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_empty_values_return_the_default(self, value: str | None) -> None:
        assert safe_css_color(value, default="#000") == "#000"


class TestMapsUrlBuilders:
    """Centralised Google Maps links used by contacts, places and events."""

    def test_directions_url_encodes_the_destination(self) -> None:
        url = build_directions_url("123 Main St, Paris")
        assert url.startswith("https://www.google.com/maps/dir/?api=1&destination=")
        assert "123%20Main%20St%2C%20Paris" in url

    def test_directions_url_accepts_a_non_string_destination(self) -> None:
        assert build_directions_url(42).endswith("=42")  # type: ignore[arg-type]

    def test_place_url_prefers_the_place_id(self) -> None:
        url = build_place_url(place_id="ChIJabc", query="ignored")
        assert url == "https://www.google.com/maps/place/?q=place_id:ChIJabc"

    def test_place_url_falls_back_to_a_search_query(self) -> None:
        url = build_place_url(query="Eiffel Tower, Paris")
        assert "maps/search/?api=1&query=Eiffel%20Tower%2C%20Paris" in url

    def test_place_url_without_input_is_empty(self) -> None:
        assert build_place_url() == ""

    def test_built_urls_survive_the_scheme_allow_list(self) -> None:
        assert safe_url(build_directions_url("Paris")) != ""
        assert safe_url(build_place_url(query="Paris")) != ""


# ============================================================================
# ESCAPING & COMPACTION
# ============================================================================


class TestEscapeHtml:
    def test_escapes_the_five_markup_characters(self) -> None:
        assert escape_html("<a href='x'>&\"</a>") == (
            "&lt;a href=&#x27;x&#x27;&gt;&amp;&quot;&lt;/a&gt;"
        )

    @pytest.mark.parametrize("value", [None, "", 0])
    def test_falsy_values_render_as_empty(self, value: object) -> None:
        assert escape_html(value) == ""  # type: ignore[arg-type]

    def test_non_string_values_are_coerced(self) -> None:
        assert escape_html(42) == "42"  # type: ignore[arg-type]


class TestCompactHtml:
    """Whitespace between tags breaks Markdown/HTML mixing in the response."""

    def test_removes_whitespace_between_tags(self) -> None:
        assert compact_html("<div>\n  <span>text</span>\n</div>") == (
            "<div><span>text</span></div>"
        )

    def test_preserves_whitespace_inside_text(self) -> None:
        assert compact_html("<p>hello   world</p>") == "<p>hello   world</p>"

    def test_empty_input_is_empty_output(self) -> None:
        assert compact_html("") == ""


class TestTruncate:
    def test_short_text_is_untouched(self) -> None:
        assert truncate("hello", 10) == "hello"

    def test_long_text_gets_the_suffix(self) -> None:
        assert truncate("abcdefghij", 8) == "abcde..."

    def test_result_never_exceeds_the_budget(self) -> None:
        assert len(truncate("x" * 200, 50)) == 50

    def test_custom_suffix(self) -> None:
        assert truncate("abcdefghij", 6, suffix="…") == "abcde…"

    @pytest.mark.parametrize("value", [None, ""])
    def test_empty_values(self, value: str | None) -> None:
        assert truncate(value) == ""


# ============================================================================
# PHONE FORMATTING
# ============================================================================


class TestPhoneFormatting:
    """Phone numbers are both displayed and turned into ``tel:`` links."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("+33 1 23 45 67 89", "+33123456789"),
            ("06.12.34.56.78", "0612345678"),
            ("(06) 12-34-56-78", "0612345678"),
        ],
    )
    def test_tel_link_keeps_only_digits_and_plus(self, raw: str, expected: str) -> None:
        assert phone_for_tel(raw) == expected

    def test_french_national_number_is_dotted(self) -> None:
        assert format_phone("0612345678") == "06.12.34.56.78"

    def test_french_international_number_is_normalised_to_national(self) -> None:
        assert format_phone("+33612345678") == "06.12.34.56.78"

    def test_foreign_number_keeps_its_shape(self) -> None:
        assert format_phone("+1 555 0100").startswith("+1")

    @pytest.mark.parametrize("value", [None, ""])
    def test_empty_values(self, value: str | None) -> None:
        assert format_phone(value) == ""
        assert phone_for_tel(value) == ""


# ============================================================================
# DURATION & SIZE
# ============================================================================


class TestFormatDuration:
    START = datetime(2026, 7, 20, 9, 0, tzinfo=UTC)

    @pytest.mark.parametrize(
        ("minutes", "language", "expected"),
        [
            (150, "fr", "2h30"),
            (120, "fr", "2h"),
            (45, "fr", "45min"),
            (150, "en", "2 hours 30 min"),
            (60, "en", "1 hour"),
            (45, "en", "45 min"),
            (150, "de", "2 Std. 30 Min."),
            (150, "zh-CN", "2小时30分钟"),
            (150, "es", "2h30"),
            (150, "it", "2h30"),
        ],
    )
    def test_localised_durations(self, minutes: int, language: str, expected: str) -> None:
        from datetime import timedelta

        end = self.START + timedelta(minutes=minutes)
        assert format_duration(self.START, end, language) == expected

    def test_iso_strings_are_accepted(self) -> None:
        assert format_duration("2026-07-20T09:00:00Z", "2026-07-20T10:30:00Z", "fr") == "1h30"

    def test_negative_duration_is_rejected(self) -> None:
        from datetime import timedelta

        assert format_duration(self.START, self.START - timedelta(hours=1)) == ""

    def test_unparsable_input_is_rejected(self) -> None:
        assert format_duration("not-a-date", "2026-07-20T10:00:00Z") == ""


class TestFormatFileSize:
    @pytest.mark.parametrize(
        ("size", "expected"),
        [
            (512, "512B"),
            (2048, "2.0KB"),
            (5 * 1024 * 1024, "5.0MB"),
            (3 * 1024 * 1024 * 1024, "3.0GB"),
        ],
    )
    def test_human_readable_units(self, size: int, expected: str) -> None:
        assert format_file_size(size) == expected

    @pytest.mark.parametrize("value", [None, 0])
    def test_missing_size_renders_nothing(self, value: int | None) -> None:
        assert format_file_size(value) == ""


class TestRenderChipStars:
    """The rating chip is fed by provider data whose type is not guaranteed."""

    def test_renders_filled_and_empty_stars(self) -> None:
        html = render_chip_stars(4)
        assert html.count("lia-chip__star-empty") == 1
        assert html.count("material-symbols-outlined") == 5

    def test_accepts_a_numeric_string(self) -> None:
        """Providers and MCP results routinely send ``"4.5"`` rather than 4.5."""
        assert render_chip_stars("4.5") != ""  # type: ignore[arg-type]

    def test_review_count_is_appended(self) -> None:
        assert "(128)" in render_chip_stars(4.5, 128)

    @pytest.mark.parametrize("value", ["not-a-number", None])
    def test_unusable_rating_renders_nothing(self, value: object) -> None:
        assert render_chip_stars(value) == ""  # type: ignore[arg-type]

    def test_out_of_range_rating_is_clamped(self) -> None:
        assert render_chip_stars(99).count("lia-chip__star-empty") == 0


# ============================================================================
# HTML FLATTENING
# ============================================================================


class TestHtmlToText:
    """Email bodies arrive as HTML and are flattened for display and TTS."""

    def test_block_elements_become_newlines(self) -> None:
        text = html_to_text("<p>First</p><p>Second</p>")
        assert "First" in text
        assert "Second" in text
        assert "<p>" not in text

    def test_style_and_script_content_is_dropped_entirely(self) -> None:
        text = html_to_text("<style>body{color:red}</style><p>Hello</p>")
        assert "color:red" not in text
        assert "Hello" in text

    def test_truncated_style_block_without_closing_tag_is_still_dropped(self) -> None:
        """Preview budgets cut bodies mid-rule; the CSS must not leak as text."""
        text = html_to_text("<p>Hi</p><style>body{color:red;font-siz")
        assert "color:red" not in text

    def test_self_closing_script_does_not_swallow_the_document(self) -> None:
        text = html_to_text('<script src="x"/><p>Visible</p>')
        assert "Visible" in text

    def test_links_are_flattened_to_their_text_by_default(self) -> None:
        text = html_to_text('<a href="https://example.com">Example</a>')
        assert text == "Example"

    def test_links_can_be_preserved_in_markdown_form(self) -> None:
        text = html_to_text('<a href="https://example.com">Example</a>', preserve_links=True)
        assert "[Example](https://example.com)" in text

    def test_entities_are_decoded(self) -> None:
        assert html_to_text("<p>caf&eacute; &amp; th&eacute;</p>") == "café & thé"

    def test_consecutive_blank_lines_are_collapsed(self) -> None:
        text = html_to_text("<p>A</p><br><br><br><br><p>B</p>")
        assert "\n\n\n" not in text

    @pytest.mark.parametrize("value", [None, ""])
    def test_empty_values(self, value: str | None) -> None:
        assert html_to_text(value) == ""


class TestFormatEmailBody:
    def test_short_body_is_not_truncated(self) -> None:
        text, truncated = format_email_body("<p>Short body</p>", max_length=500)
        assert text == "Short body"
        assert truncated is False

    def test_long_body_is_truncated_and_flagged(self) -> None:
        text, truncated = format_email_body("word " * 500, max_length=100)
        assert truncated is True
        assert len(text) <= 100

    def test_truncation_prefers_a_word_boundary(self) -> None:
        text, _ = format_email_body("alpha bravo charlie delta echo foxtrot", max_length=20)
        assert not text.endswith("cha")

    @pytest.mark.parametrize("value", [None, ""])
    def test_empty_values(self, value: str | None) -> None:
        assert format_email_body(value) == ("", False)


class TestMarkdownLinksToHtml:
    """LLM answers carry Markdown links that become real anchors."""

    def test_converts_a_markdown_link(self) -> None:
        html = markdown_links_to_html("See [Example](https://example.com) now")
        assert '<a href="https://example.com" target="_blank" rel="noopener">Example</a>' in html

    def test_surrounding_text_is_escaped(self) -> None:
        html = markdown_links_to_html("<b>bold</b> [x](https://example.com)")
        assert "&lt;b&gt;" in html

    def test_long_url_without_label_is_shortened(self) -> None:
        long_url = "https://example.com/" + "a" * 80
        html = markdown_links_to_html(f"[]({long_url})", url_shorten_threshold=50)
        assert "Lien" in html
        assert "a" * 80 not in html.split("</a>")[0].split(">")[-1]

    def test_javascript_link_loses_its_anchor(self) -> None:
        """A model-authored ``javascript:`` link must render as inert text."""
        html = markdown_links_to_html("[click](javascript:alert(1))")
        assert "<a " not in html
        assert "click" in html

    def test_text_without_links_is_escaped_and_returned(self) -> None:
        assert markdown_links_to_html("a < b") == "a &lt; b"
