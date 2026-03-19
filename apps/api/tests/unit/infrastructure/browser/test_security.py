"""
Unit tests for browser security policy.

Phase: evolution F7 — Browser Control (Playwright)
"""

import pytest

from src.core.constants import BROWSER_BLOCKED_SCHEMES
from src.infrastructure.browser.security import (
    _ALLOWED_KEYS,
    _MAX_FILL_VALUE_LENGTH,
    BrowserSecurityPolicy,
)


class TestBrowserSecurityPolicy:
    """Tests for BrowserSecurityPolicy."""

    def setup_method(self):
        """Create a fresh policy for each test."""
        self.policy = BrowserSecurityPolicy()

    # ========================================================================
    # validate_navigation_url
    # ========================================================================

    @pytest.mark.asyncio
    async def test_validate_blocked_scheme_javascript(self):
        """Blocked scheme javascript: returns invalid."""
        is_valid, error = await self.policy.validate_navigation_url("javascript:alert(1)")
        assert not is_valid
        assert "Blocked URL scheme" in error

    @pytest.mark.asyncio
    async def test_validate_blocked_scheme_file(self):
        """Blocked scheme file: returns invalid."""
        is_valid, error = await self.policy.validate_navigation_url("file:///etc/passwd")
        assert not is_valid
        assert "Blocked URL scheme" in error

    @pytest.mark.asyncio
    async def test_validate_blocked_scheme_data(self):
        """Blocked scheme data: returns invalid."""
        is_valid, error = await self.policy.validate_navigation_url("data:text/html,<h1>Hi</h1>")
        assert not is_valid
        assert "Blocked URL scheme" in error

    @pytest.mark.asyncio
    async def test_validate_blocked_schemes_complete(self):
        """All schemes in BROWSER_BLOCKED_SCHEMES are blocked."""
        for scheme in BROWSER_BLOCKED_SCHEMES:
            is_valid, _ = await self.policy.validate_navigation_url(f"{scheme}://something")
            assert not is_valid, f"Scheme {scheme} should be blocked"

    # ========================================================================
    # validate_key
    # ========================================================================

    def test_validate_key_allowed(self):
        """Allowed keys return True."""
        for key in _ALLOWED_KEYS:
            assert self.policy.validate_key(key), f"Key {key} should be allowed"

    def test_validate_key_blocked(self):
        """Non-whitelisted keys return False."""
        assert not self.policy.validate_key("F12")
        assert not self.policy.validate_key("Meta")
        assert not self.policy.validate_key("Control+C")
        assert not self.policy.validate_key("")
        assert not self.policy.validate_key("a")

    # ========================================================================
    # sanitize_fill_value
    # ========================================================================

    def test_sanitize_normal_value(self):
        """Normal text passes through unchanged."""
        assert self.policy.sanitize_fill_value("Hello World") == "Hello World"

    def test_sanitize_strips_control_chars(self):
        """Control characters are stripped."""
        # \x00 (null), \x07 (bell), \x1f (unit separator)
        result = self.policy.sanitize_fill_value("Hello\x00World\x07Test\x1f")
        assert result == "HelloWorldTest"

    def test_sanitize_preserves_newlines_tabs(self):
        """Newlines and tabs are preserved (for textareas)."""
        result = self.policy.sanitize_fill_value("Line1\nLine2\tTabbed")
        assert "\n" in result
        assert "\t" in result

    def test_sanitize_enforces_max_length(self):
        """Values exceeding max length are truncated."""
        long_value = "A" * (_MAX_FILL_VALUE_LENGTH + 1000)
        result = self.policy.sanitize_fill_value(long_value)
        assert len(result) == _MAX_FILL_VALUE_LENGTH

    def test_sanitize_empty_value(self):
        """Empty value returns empty."""
        assert self.policy.sanitize_fill_value("") == ""


class TestBlockedDomains:
    """Tests for custom domain blocking via settings."""

    def test_blocked_domains_parsed(self):
        """Blocked domains from settings are parsed correctly."""
        policy = BrowserSecurityPolicy()
        # Default is empty — no custom domains blocked
        assert isinstance(policy._blocked_domains, set)
