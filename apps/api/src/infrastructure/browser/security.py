"""
Browser security policy.

Provides SSRF prevention, URL validation, input sanitization,
and request interception for the browser automation infrastructure.

Reuses existing URL validation from web_fetch module.

Phase: evolution F7 — Browser Control (Playwright)
"""

from __future__ import annotations

import re
import time
from collections import OrderedDict
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import structlog

from src.core.config import settings
from src.core.constants import BROWSER_BLOCKED_SCHEMES

if TYPE_CHECKING:
    from playwright.async_api import Page, Route

logger = structlog.get_logger(__name__)


class _HostVerdictCache:
    """Bounded, expiring cache of per-host SSRF verdicts (SEC-032).

    The interceptor runs on EVERY request a page makes — a content-heavy page
    easily issues a few hundred — and the underlying check resolves DNS. Without
    a cache the guard would add a lookup per sub-resource and make browsing
    unusably slow, which is the kind of cost that gets a security control turned
    off.

    Entries expire quickly on purpose: the TTL is exactly the window in which a
    rebinding attack could reuse a stale "allowed" verdict.
    """

    def __init__(self, *, ttl_seconds: int, max_hosts: int) -> None:
        self._ttl = ttl_seconds
        self._max = max_hosts
        self._entries: OrderedDict[str, tuple[float, bool]] = OrderedDict()

    def get(self, host: str) -> bool | None:
        """Return a cached verdict, or None when absent or expired."""
        entry = self._entries.get(host)
        if entry is None:
            return None
        expires_at, allowed = entry
        if time.monotonic() >= expires_at:
            del self._entries[host]
            return None
        self._entries.move_to_end(host)
        return allowed

    def set(self, host: str, allowed: bool) -> None:
        """Record a verdict, evicting the least recently used host when full."""
        self._entries[host] = (time.monotonic() + self._ttl, allowed)
        self._entries.move_to_end(host)
        while len(self._entries) > self._max:
            self._entries.popitem(last=False)


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
        self._host_verdicts = _HostVerdictCache(
            ttl_seconds=settings.browser_ssrf_cache_ttl_seconds,
            max_hosts=settings.browser_ssrf_cache_max_hosts,
        )

    async def _host_is_reachable(self, url: str) -> bool:
        """Whether a URL's host resolves to a public address (SEC-032).

        Verdicts are cached per host: this runs on every request a page makes,
        and the check behind it performs a DNS resolution.

        Args:
            url: URL about to be requested by the page.

        Returns:
            True when the host may be contacted.
        """
        host = (urlparse(url).hostname or "").lower()
        if not host:
            return False

        cached = self._host_verdicts.get(host)
        if cached is not None:
            return cached

        # Lazy import to avoid a circular dependency at module load.
        from src.domains.agents.web_fetch.url_validator import validate_url

        result = await validate_url(url)
        self._host_verdicts.set(host, result.valid)
        return result.valid

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
        """Register a request interceptor on every request the page makes.

        ``validate_navigation_url`` only covers the URL the agent explicitly
        asks for. Everything the page does next reaches this handler instead:
        redirects, sub-resources, iframes, workers, XHR, and navigations caused
        by a click or a form submission. It used to check the scheme and a
        "download" substring, forward everything else, and — on any exception —
        forward the request too. So a public page could redirect to a loopback,
        private, link-local or cloud-metadata address and the browser would
        fetch it (SEC-032).

        Each request now resolves its host and is refused unless it is public,
        with verdicts cached per host so the DNS cost stays bearable, and any
        failure aborts instead of forwarding.

        Enforcement is behind ``BROWSER_SSRF_ENFORCE`` and starts OFF: a real
        page also pulls CDNs, fonts and analytics, so the block rate is observed
        (``browser_request_ssrf_report_only``) before it is trusted. In
        report-only the request proceeds and the decision is logged.

        Args:
            page: The Playwright page to intercept requests on.
        """
        enforce = settings.browser_ssrf_enforce

        async def _intercept(route: Route) -> None:
            request = route.request
            url = request.url

            try:
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

                # SEC-032: the destination itself, not just its scheme.
                if not await self._host_is_reachable(url):
                    if enforce:
                        logger.warning(
                            "browser_request_ssrf_blocked",
                            url=url[:200],
                            resource_type=request.resource_type,
                        )
                        await route.abort("blockedbyclient")
                        return
                    logger.warning(
                        "browser_request_ssrf_report_only",
                        url=url[:200],
                        resource_type=request.resource_type,
                        msg="would be blocked once BROWSER_SSRF_ENFORCE is enabled",
                    )

                await route.continue_()

            except Exception as exc:
                # Fail CLOSED. This used to forward the request, so any failure
                # in the guard — a DNS error, a malformed URL, a Playwright
                # hiccup — silently disabled it for that request. A blocked
                # sub-resource degrades a page; a forwarded one can reach an
                # internal service.
                logger.warning(
                    "browser_request_interceptor_failed",
                    url=url[:200],
                    error=str(exc),
                )
                await route.abort("blockedbyclient")

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
