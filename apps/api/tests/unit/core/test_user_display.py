"""Unit tests for the shared user display-name resolution helper."""

from src.core.user_display import resolve_user_display_name


class TestResolveUserDisplayName:
    """Fallback chain: full_name first word → email local part → fallback."""

    def test_full_name_first_word(self):
        assert resolve_user_display_name("Paul Lemoine", "p@example.com") == "Paul"

    def test_single_word_full_name(self):
        assert resolve_user_display_name("Paul", None) == "Paul"

    def test_whitespace_full_name_falls_back_to_email(self):
        assert resolve_user_display_name("   ", "user@example.com") == "user"

    def test_none_full_name_falls_back_to_email(self):
        assert resolve_user_display_name(None, "user@example.com") == "user"

    def test_no_sources_returns_default_fallback(self):
        assert resolve_user_display_name(None, None) == ""

    def test_custom_fallback(self):
        assert resolve_user_display_name(None, None, fallback="there") == "there"

    def test_empty_email_returns_fallback(self):
        assert resolve_user_display_name(None, "", fallback="x") == "x"
