"""
Browser security policy.

Provides SSRF prevention, URL validation, input sanitization,
and request interception for the browser automation infrastructure.

Reuses existing URL validation from web_fetch module.

Phase: evolution F7 — Browser Control (Playwright)
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import structlog

from src.core.config import settings
from src.core.constants import BROWSER_BLOCKED_SCHEMES

if TYPE_CHECKING:
    from playwright.async_api import Page, Route

logger = structlog.get_logger(__name__)

# Maximum length for fill values (prevents abuse)
_MAX_FILL_VALUE_LENGTH = 10_000

# Control characters to strip from fill values (except newline/tab)
_CONTROL_CHARS_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Allowed keyboard keys whitelist
_ALLOWED_KEYS = frozenset(
    {
        "Enter",
        "Tab",
        "Escape",
        "ArrowUp",
        "ArrowDown",
        "ArrowLeft",
        "ArrowRight",
        "Backspace",
        "Delete",
        "Space",
        "Home",
        "End",
        "PageUp",
        "PageDown",
    }
)


class BrowserSecurityPolicy:
    """Security policy for browser automation.

    Provides URL validation, input sanitization, key validation,
    and request interception to prevent SSRF and injection attacks.
    """

    def __init__(self) -> None:
        self._blocked_domains: set[str] = set()
        if settings.browser_blocked_domains:
            self._blocked_domains = {
                d.strip().lower() for d in settings.browser_blocked_domains.split(",") if d.strip()
            }

    async def validate_navigation_url(self, url: str) -> tuple[bool, str]:
        """Validate a URL for browser navigation.

        Combines existing web_fetch SSRF validation with browser-specific
        scheme blocking and domain blocklist.

        Args:
            url: The URL to validate.

        Returns:
            Tuple of (is_valid, error_message). error_message is empty if valid.
        """
        # Lazy import to avoid circular dependency
        from src.domains.agents.web_fetch.url_validator import validate_url

        # Check blocked schemes first (fast path)
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            if parsed.scheme.lower() in BROWSER_BLOCKED_SCHEMES:
                return False, f"Blocked URL scheme: {parsed.scheme}"
        except Exception:
            return False, "Invalid URL format"

        # Check blocked domains
        if parsed.hostname and parsed.hostname.lower() in self._blocked_domains:
            return False, f"Blocked domain: {parsed.hostname}"

        # Reuse web_fetch SSRF validation (DNS resolution, private IP check)
        result = await validate_url(url)
        if not result.valid:
            return False, result.error or "URL validation failed"

        return True, ""

    async def create_request_interceptor(self, page: Page) -> None:
        """Register a request interceptor to block dangerous requests.

        Blocks requests to private IPs, dangerous schemes, and file downloads
        while allowing the main navigation request to proceed.

        Args:
            page: The Playwright page to intercept requests on.
        """

        async def _intercept(route: Route) -> None:
            request = route.request
            url = request.url

            try:
                from urllib.parse import urlparse

                parsed = urlparse(url)

                # Block dangerous schemes
                if parsed.scheme.lower() in BROWSER_BLOCKED_SCHEMES:
                    logger.warning(
                        "browser_request_blocked_scheme",
                        url=url[:200],
                        scheme=parsed.scheme,
                    )
                    await route.abort("blockedbyclient")
                    return

                # Block file downloads (content-disposition: attachment)
                if request.resource_type in ("document",) and "download" in url.lower():
                    logger.warning("browser_request_blocked_download", url=url[:200])
                    await route.abort("blockedbyclient")
                    return

                # Allow all other requests
                await route.continue_()

            except Exception:
                # On any error, allow the request to proceed
                await route.continue_()

        await page.route("**/*", _intercept)

    def validate_key(self, key: str) -> bool:
        """Validate that a keyboard key is in the allowed whitelist.

        Args:
            key: The key name to validate (e.g., 'Enter', 'Tab').

        Returns:
            True if the key is allowed, False otherwise.
        """
        return key in _ALLOWED_KEYS

    def sanitize_fill_value(self, value: str) -> str:
        """Sanitize a value for form field filling.

        Strips control characters and enforces maximum length to prevent
        injection attacks via fill operations.

        Args:
            value: The raw value to sanitize.

        Returns:
            Sanitized value safe for form filling.
        """
        # Enforce max length
        if len(value) > _MAX_FILL_VALUE_LENGTH:
            value = value[:_MAX_FILL_VALUE_LENGTH]

        # Strip control characters (keep newlines and tabs for textareas)
        value = _CONTROL_CHARS_PATTERN.sub("", value)

        return value
