"""Tests for Telegram message formatter."""

from src.infrastructure.channels.telegram.formatter import (
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

    def test_french_default(self) -> None:
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

    def test_unknown_language_falls_back_to_french(self) -> None:
        msg = get_bot_message("otp_success", "ja")
        # Should fallback to French
        assert "lié avec succès" in msg

    def test_unknown_key_returns_empty(self) -> None:
        msg = get_bot_message("nonexistent_key", "fr")
        assert msg == ""

    def test_all_message_keys_exist(self) -> None:
        """All expected message keys should be defined."""
        expected_keys = [
            "otp_success",
            "otp_invalid",
            "otp_blocked",
            "processing",
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
