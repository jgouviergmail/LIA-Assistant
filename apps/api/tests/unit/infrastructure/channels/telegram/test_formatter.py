"""Tests for Telegram message formatter."""

import pytest

from src.core.config import settings
from src.infrastructure.channels.telegram.formatter import (
    TELEGRAM_BOT_MESSAGES,
    format_notification,
    get_bot_message,
    markdown_to_telegram_html,
    split_message,
    strip_html_cards,
)


class TestMarkdownToTelegramHTML:
    """Tests for markdown → Telegram HTML conversion."""

    def test_bold_double_asterisks(self) -> None:
        result = markdown_to_telegram_html("**bold text**")
        assert result == "<b>bold text</b>"

    def test_bold_double_underscores(self) -> None:
        result = markdown_to_telegram_html("__bold text__")
        assert result == "<b>bold text</b>"

    def test_strikethrough(self) -> None:
        result = markdown_to_telegram_html("~~deleted~~")
        assert result == "<s>deleted</s>"

    def test_code_inline(self) -> None:
        result = markdown_to_telegram_html("`code`")
        assert result == "<code>code</code>"

    def test_link(self) -> None:
        result = markdown_to_telegram_html("[Google](https://google.com)")
        assert result == '<a href="https://google.com">Google</a>'

    def test_html_entities_escaped(self) -> None:
        """Should escape existing HTML entities before conversion."""
        result = markdown_to_telegram_html("<script>alert('xss')</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_mixed_formatting(self) -> None:
        """Should handle multiple formatting types in one message."""
        text = "**bold** and `code` and [link](https://example.com)"
        result = markdown_to_telegram_html(text)
        assert "<b>bold</b>" in result
        assert "<code>code</code>" in result
        assert '<a href="https://example.com">link</a>' in result

    def test_plain_text_passthrough(self) -> None:
        """Plain text without markdown should pass through unchanged (except HTML escaping)."""
        result = markdown_to_telegram_html("Hello world")
        assert result == "Hello world"

    def test_ampersand_escaped(self) -> None:
        result = markdown_to_telegram_html("A & B")
        assert result == "A &amp; B"

    def test_references_are_read_as_the_chat_reads_them(self) -> None:
        """A value a card draws as itself reaches Markdown as ``&#91;``: Telegram
        shows « [ », and a bracket or an underscore it spells never opens a
        link or an italic."""
        result = markdown_to_telegram_html("&#91;x&#93;(https://e.example) &#95;y&#95; & z")
        assert result == "[x](https://e.example) _y_ &amp; z"

    @pytest.mark.parametrize(
        ("reference", "drawn"),
        [
            ("&#x26;", "&amp;"),
            ("&#233;", "é"),
            ("&eacute;", "é"),
            ("&#0;", "\ufffd"),
            ("&#xD800;", "\ufffd"),
            ("&unknownname;", "&amp;unknownname;"),
            ("&copy=2", "&amp;copy=2"),
        ],
    )
    def test_every_reference_is_read_and_none_is_refused(self, reference: str, drawn: str) -> None:
        """What the chat draws is what Telegram shows; an invalid reference
        (``&#0;``) got the whole message refused before it was read."""
        assert markdown_to_telegram_html(f"a {reference} b") == f"a {drawn} b"

    def test_a_reference_in_code_is_shown_as_typed(self) -> None:
        """The chat shows ``&#91;`` in a code span; Telegram drew « [ »."""
        assert markdown_to_telegram_html("tape `&#91;`") == "tape <code>&amp;#91;</code>"

    def test_a_code_block_is_drawn_whole(self) -> None:
        """Its text as typed: no emphasis, no escape lost."""
        result = markdown_to_telegram_html("```py\na*b*c <x> &#42;\n```\nfin")
        assert result == "<pre>a*b*c &lt;x&gt; &amp;#42;\n</pre>fin"

    def test_italics_never_enter_a_link_s_address(self) -> None:
        """The italic rule ran before the link rule: ``<i>`` landed inside the
        href of the one link a card draws (review 14)."""
        result = markdown_to_telegram_html("[Lien](https://drive.example/file/d/1a_B2c_D3/view)")
        assert result == '<a href="https://drive.example/file/d/1a_B2c_D3/view">Lien</a>'

    @pytest.mark.parametrize(
        "address",
        ["mailto:_a_@b.example", "https://a_b.example/_c_/", "https://e.example/*x*"],
        ids=["mail", "host_the_reader_does_not_read_as_a_url", "star"],
    )
    def test_no_address_meets_the_emphasis_rules(self, address: str) -> None:
        """Only the addresses the reader reads as bare URLs had their marks
        kept: ``mailto:_a_@…`` still drew ``<i>`` inside its href (review 14)."""
        assert markdown_to_telegram_html(f"[x]({address})") == f'<a href="{address}">x</a>'

    def test_emphasis_around_a_link_still_draws(self) -> None:
        assert markdown_to_telegram_html("*a [b](https://e.example/x) c*") == (
            '<i>a <a href="https://e.example/x">b</a> c</i>'
        )

    def test_a_bare_url_keeps_its_marks(self) -> None:
        assert markdown_to_telegram_html("voir https://a.example/_x_/y*z*") == (
            "voir https://a.example/_x_/y*z*"
        )

    @pytest.mark.parametrize(
        ("markdown", "drawn"),
        [
            ("max_results: 10, page_token", "max_results: 10, page_token"),
            ("send_email_tool: 3 items", "send_email_tool: 3 items"),
            ("_word_ et __gras__", "<i>word</i> et <b>gras</b>"),
            ("*mot* et **gras**", "<i>mot</i> et <b>gras</b>"),
        ],
    )
    def test_an_underscore_inside_a_word_opens_nothing(self, markdown: str, drawn: str) -> None:
        """CommonMark's rule: Telegram put ``<i>`` across two names."""
        assert markdown_to_telegram_html(markdown) == drawn

    @pytest.mark.parametrize(
        "markdown",
        ["[x](javascript:alert(1))", "[x](tg://resolve?domain=x)", "[x](ftp://a.example)"],
    )
    def test_only_a_web_or_mail_address_becomes_a_link(self, markdown: str) -> None:
        """A scheme Telegram does not draw gets the whole message refused."""
        assert "<a " not in markdown_to_telegram_html(markdown)

    def test_a_mail_link_is_drawn_and_a_quote_in_an_address_is_escaped(self) -> None:
        assert markdown_to_telegram_html(
            '[écrire](mailto:a@b.example) [q](https://a.example/"x)'
        ) == ('<a href="mailto:a@b.example">écrire</a> <a href="https://a.example/&quot;x">q</a>')


class TestSplitMessage:
    """Tests for message splitting."""

    def test_short_message_no_split(self) -> None:
        """Short messages should not be split."""
        result = split_message("Hello world", max_length=100)
        assert len(result) == 1
        assert result[0] == "Hello world"

    def test_exact_limit_no_split(self) -> None:
        """Message at exact limit should not be split."""
        text = "x" * 100
        result = split_message(text, max_length=100)
        assert len(result) == 1

    def test_split_at_paragraph_boundary(self) -> None:
        """Should prefer splitting at paragraph boundaries."""
        text = "First paragraph.\n\nSecond paragraph."
        result = split_message(text, max_length=25)
        assert len(result) == 2
        assert result[0] == "First paragraph."
        assert result[1] == "Second paragraph."

    def test_split_at_line_boundary(self) -> None:
        """Should split at line boundary when no paragraph break fits."""
        text = "Line one.\nLine two.\nLine three."
        result = split_message(text, max_length=20)
        assert len(result) >= 2

    def test_hard_split_when_no_boundary(self) -> None:
        """Should hard-split at max_length when no good boundary exists."""
        text = "a" * 200
        result = split_message(text, max_length=100)
        assert len(result) == 2
        assert len(result[0]) == 100
        assert len(result[1]) == 100

    def test_empty_string(self) -> None:
        """Empty string should return single empty chunk."""
        result = split_message("", max_length=100)
        assert len(result) == 1
        assert result[0] == ""

    def test_multiple_chunks(self) -> None:
        """Long message should be split into multiple chunks."""
        text = "\n\n".join([f"Paragraph {i}" for i in range(20)])
        result = split_message(text, max_length=50)
        assert len(result) > 1
        # All chunks should be within limit
        for chunk in result:
            assert len(chunk) <= 50


class TestFormatNotification:
    """Tests for notification formatting."""

    def test_basic_notification(self) -> None:
        result = format_notification("Title", "Body text")
        assert result == "<b>Title</b>\n\nBody text"

    def test_notification_structure(self) -> None:
        """Should have title on first line, body after blank line."""
        result = format_notification("Title", "Body")
        assert result == "<b>Title</b>\n\nBody"

    def test_notification_html_escaping(self) -> None:
        """Should escape HTML entities in title and body."""
        result = format_notification("T & P", "15°C & sunny <today>")
        assert result == "<b>T &amp; P</b>\n\n15°C &amp; sunny &lt;today&gt;"


class TestGetBotMessage:
    """Tests for localized bot messages."""

    def test_french(self) -> None:
        msg = get_bot_message("otp_success", "fr")
        assert "lié avec succès" in msg

    def test_english(self) -> None:
        msg = get_bot_message("otp_success", "en")
        assert "linked successfully" in msg

    def test_all_languages_have_otp_success(self) -> None:
        """All 6 languages should have the otp_success message."""
        for lang in ["fr", "en", "es", "de", "it", "zh"]:
            msg = get_bot_message("otp_success", lang)
            assert len(msg) > 0, f"Missing otp_success for {lang}"

    def test_an_unknown_language_reads_as_the_instance_default(self) -> None:
        """An unsupported code reads as the instance default (ADR-323)."""
        assert (
            get_bot_message("otp_success", "ja")
            == TELEGRAM_BOT_MESSAGES["otp_success"][settings.default_language]
        )

    def test_a_chinese_account_reads_chinese(self) -> None:
        """The tables were keyed on the frontend's `zh`: a zh-CN account read FRENCH."""
        assert (
            get_bot_message("otp_success", "zh-CN") == TELEGRAM_BOT_MESSAGES["otp_success"]["zh-CN"]
        )

    def test_unknown_key_returns_empty(self) -> None:
        msg = get_bot_message("nonexistent_key", "fr")
        assert msg == ""

    def test_all_message_keys_exist(self) -> None:
        """All expected message keys should be defined."""
        expected_keys = [
            "otp_success",
            "otp_invalid",
            "otp_blocked",
            "busy",
            "unbound",
            "error",
            "voice_empty",
            "voice_too_long",
        ]
        for key in expected_keys:
            msg = get_bot_message(key, "fr")
            assert len(msg) > 0, f"Missing message for key: {key}"


# =============================================================================
# strip_html_cards
# =============================================================================


class TestStripHtmlCards:
    """Tests for HTML card stripping (Telegram channel cleanup)."""

    def test_plain_text_unchanged(self) -> None:
        """Plain text without HTML should pass through unchanged."""
        text = "Demain il fera 22°C avec du soleil."
        assert strip_html_cards(text) == text

    def test_strips_div_block_at_end(self) -> None:
        """Should remove <div> blocks appended after LLM text."""
        text = (
            "Voici la météo.\n\n"
            '<div class="weather-card">'
            '<div class="inner">22°C</div>'
            "</div>"
        )
        assert strip_html_cards(text) == "Voici la météo."

    def test_strips_complex_nested_html(self) -> None:
        """Should remove complex nested HTML card structures."""
        text = (
            "Réponse de l'agent.\n\n"
            '<div class="registry-card" style="margin:8px">'
            '<div class="header"><b>Météo</b></div>'
            '<div class="body"><span>Ensoleillé</span></div>'
            "</div>"
        )
        result = strip_html_cards(text)
        assert result == "Réponse de l'agent."
        assert "<div" not in result

    def test_preserves_inline_html_entities(self) -> None:
        """Should preserve escaped HTML entities (not real tags)."""
        text = "Température : 15°C &amp; ensoleillé"
        assert strip_html_cards(text) == text

    def test_empty_string(self) -> None:
        """Empty string should return empty string."""
        assert strip_html_cards("") == ""

    def test_only_html(self) -> None:
        """Text that is only HTML should return empty."""
        text = '\n\n<div class="card">content</div>'
        assert strip_html_cards(text) == ""

    def test_multiple_div_blocks(self) -> None:
        """Should strip all HTML card blocks after the response."""
        text = (
            "Voici les résultats.\n\n"
            '<div class="card-1">Card 1</div>'
            '<div class="card-2">Card 2</div>'
        )
        result = strip_html_cards(text)
        assert result == "Voici les résultats."

    def test_markdown_with_angle_brackets(self) -> None:
        """Should not strip markdown text that uses < or > (not card blocks)."""
        text = "Use `a < b` to compare values."
        assert strip_html_cards(text) == text

    def test_preserves_comparison_operators(self) -> None:
        """Should not strip < and > used as comparison operators."""
        text = "Use a < b and c > d"
        assert strip_html_cards(text) == text

    def test_strips_standalone_img_tags(self) -> None:
        """Should strip standalone img tags."""
        text = "Voici la photo.\n\n<img src='photo.jpg' />"
        result = strip_html_cards(text)
        assert "<img" not in result

    def test_strips_email_card_fragments(self) -> None:
        """Should strip orphaned email card HTML (closing tags + <a> links)."""
        text = (
            "Voici vos emails."
            "</div></span></span></div></div></div>"
            '<a href="https://mail.google.com/" class="lia-email__subject"'
            ' target="_blank" rel="noopener">'
            "\n                        Email Subject"
            "\n                    </a></div>"
        )
        result = strip_html_cards(text)
        assert result == "Voici vos emails."
        assert "<a" not in result
        assert "</div>" not in result
        assert "Email Subject" not in result

    def test_strips_orphaned_closing_tags_with_content_after(self) -> None:
        """Should strip from first closing tag, including any content after."""
        text = "Réponse.</span></span></div></div>"
        result = strip_html_cards(text)
        assert result == "Réponse."
