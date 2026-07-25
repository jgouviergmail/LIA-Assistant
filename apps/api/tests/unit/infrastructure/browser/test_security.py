"""
Unit tests for browser security policy.

Phase: evolution F7 — Browser Control (Playwright)
"""

import time
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest
from structlog.testing import capture_logs

from src.core.constants import BROWSER_BLOCKED_SCHEMES
from src.infrastructure.browser.security import (
    _ALLOWED_KEYS,
    _MAX_FILL_VALUE_LENGTH,
    BrowserSecurityPolicy,
    _HostVerdictCache,
)


def _force_verdict(monkeypatch: pytest.MonkeyPatch, *, valid: bool) -> list[str]:
    """Replace the SSRF validator with a recorder — no DNS in unit tests.

    Args:
        monkeypatch: pytest fixture.
        valid: Verdict the stub returns.

    Returns:
        The list of URLs the validator was actually asked about, which is how
        the cache tests count resolutions.
    """
    seen: list[str] = []

    async def _fake_validate_url(url: str):
        seen.append(url)
        return MagicMock(valid=valid, error=None if valid else "blocked")

    monkeypatch.setattr(
        "src.domains.agents.web_fetch.url_validator.validate_url",
        _fake_validate_url,
    )
    return seen


def _make_route(url: str, resource_type: str = "document") -> MagicMock:
    """Build a mock Playwright ``Route`` for the request interceptor.

    ``Route.abort()`` and ``Route.continue_()`` are async; ``request.url`` and
    ``request.resource_type`` are plain attributes. No network is involved.

    Args:
        url: URL carried by the intercepted request.
        resource_type: Playwright resource type ("document", "image", ...).

    Returns:
        MagicMock route with async ``abort``/``continue_`` recorders.
    """
    route = MagicMock()
    route.request.url = url
    route.request.resource_type = resource_type
    route.abort = AsyncMock()
    route.continue_ = AsyncMock()
    return route


async def _run_interceptor(policy: BrowserSecurityPolicy, route: MagicMock) -> None:
    """Register the interceptor on a mock page and invoke it with ``route``.

    The policy registers its handler through ``page.route("**/*", handler)``;
    this helper extracts that handler and calls it directly, so the behaviour
    under test is the interceptor itself — not Playwright's routing.

    Args:
        policy: Policy under test.
        route: Mock route to feed the handler.
    """
    page = MagicMock()
    page.route = AsyncMock()
    await policy.create_request_interceptor(page)
    handler = page.route.call_args.args[1]
    await handler(route)


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


class TestRequestInterceptor:
    """``create_request_interceptor`` — the guard on everything a page does.

    ``validate_navigation_url`` covers only the URL the agent explicitly asks
    for. Redirects, sub-resources, iframes, workers, XHR and click-driven
    navigations reach the interceptor instead, and it used to check the scheme
    and a "download" substring before forwarding everything else — including to
    loopback, private and cloud-metadata addresses (SEC-032).

    Enforcement is asserted with ``BROWSER_SSRF_ENFORCE`` forced on; the shipped
    default is report-only, covered separately below.
    """

    def setup_method(self):
        """Create a fresh policy for each test."""
        self.policy = BrowserSecurityPolicy()

    @pytest.mark.asyncio
    async def test_blocked_scheme_is_aborted(self):
        """A blocked scheme is aborted, not forwarded."""
        route = _make_route("javascript:alert(1)")
        await _run_interceptor(self.policy, route)
        route.abort.assert_awaited_once_with("blockedbyclient")
        route.continue_.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_document_download_is_aborted(self):
        """A document request whose URL mentions a download is aborted."""
        route = _make_route("https://example.com/download/report.pdf")
        await _run_interceptor(self.policy, route)
        route.abort.assert_awaited_once_with("blockedbyclient")
        route.continue_.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_public_request_is_forwarded(self, monkeypatch):
        """A normal public request is forwarded (nominal path).

        Guards the fix against being a blanket refusal — a browser that blocks
        every sub-resource renders nothing.
        """
        _force_verdict(monkeypatch, valid=True)
        route = _make_route("https://example.com/article", resource_type="document")

        await _run_interceptor(self.policy, route)

        route.continue_.assert_awaited_once()
        route.abort.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("url", "resource_type"),
        [
            ("http://127.0.0.1:8000/internal", "xhr"),
            ("http://169.254.169.254/latest/meta-data/", "fetch"),
            ("http://10.0.0.5/admin", "document"),
            ("http://[::1]:8000/internal", "script"),
        ],
        ids=["loopback", "cloud-metadata", "private", "ipv6-loopback"],
    )
    async def test_non_public_destination_is_aborted(self, monkeypatch, url, resource_type):
        """Was FORWARDED: a sub-resource on an internal address is now refused.

        This is the SEC-032 defect inverted. The interceptor's own docstring
        used to claim it blocked private IPs while checking only the scheme.
        """
        monkeypatch.setattr(
            "src.infrastructure.browser.security.settings.browser_ssrf_enforce",
            True,
            raising=False,
        )
        policy = BrowserSecurityPolicy()
        route = _make_route(url, resource_type=resource_type)

        await _run_interceptor(policy, route)

        route.abort.assert_awaited_once_with("blockedbyclient")
        route.continue_.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_interceptor_exception_fails_closed(self, monkeypatch):
        """Was FORWARDED: an error inside the guard now aborts.

        A failure in the guard — DNS error, malformed URL, Playwright hiccup —
        used to silently disable it for that request. A blocked sub-resource
        degrades a page; a forwarded one can reach an internal service.
        """
        route = _make_route("https://example.com/asset.js", resource_type="script")
        type(route.request).resource_type = PropertyMock(side_effect=RuntimeError("boom"))

        await _run_interceptor(self.policy, route)

        route.abort.assert_awaited_once_with("blockedbyclient")
        route.continue_.assert_not_awaited()


class TestReportOnlyMode:
    """The shipped default observes before it blocks."""

    @pytest.mark.asyncio
    async def test_report_only_forwards_but_logs(self, monkeypatch):
        """With enforcement off, a would-be block is logged and forwarded.

        Real pages pull CDNs, fonts and analytics; the block rate has to be
        measured on live traffic before a wrong verdict starts breaking
        rendering. The log line is the measurement.
        """
        monkeypatch.setattr(
            "src.infrastructure.browser.security.settings.browser_ssrf_enforce",
            False,
            raising=False,
        )
        policy = BrowserSecurityPolicy()
        route = _make_route("http://127.0.0.1:8000/internal", resource_type="xhr")

        with capture_logs() as logs:
            await _run_interceptor(policy, route)

        route.continue_.assert_awaited_once()
        route.abort.assert_not_awaited()
        assert any(entry["event"] == "browser_request_ssrf_report_only" for entry in logs)


class TestHostVerdictCache:
    """One DNS resolution per host, not per request."""

    @pytest.mark.asyncio
    async def test_repeated_hosts_resolve_once(self, monkeypatch):
        """A page pulling many sub-resources must not pay a lookup each time.

        Without this the guard adds a DNS round-trip per request — hundreds on
        a content-heavy page — which is the kind of cost that gets a security
        control switched off.
        """
        calls = _force_verdict(monkeypatch, valid=True)
        policy = BrowserSecurityPolicy()

        for path in ("/a.js", "/b.css", "/c.png", "/d.woff"):
            await _run_interceptor(policy, _make_route(f"https://cdn.example.com{path}"))

        assert len(calls) == 1, f"expected one resolution, got {len(calls)}"

    @pytest.mark.asyncio
    async def test_distinct_hosts_are_resolved_separately(self, monkeypatch):
        """Caching is per host — a new host is always checked."""
        calls = _force_verdict(monkeypatch, valid=True)
        policy = BrowserSecurityPolicy()

        await _run_interceptor(policy, _make_route("https://a.example.com/x"))
        await _run_interceptor(policy, _make_route("https://b.example.com/x"))

        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_expired_entry_is_revalidated(self, monkeypatch):
        """The TTL is the rebinding window — it must actually expire."""
        calls = _force_verdict(monkeypatch, valid=True)
        monkeypatch.setattr(
            "src.infrastructure.browser.security.settings.browser_ssrf_cache_ttl_seconds",
            1,
            raising=False,
        )
        policy = BrowserSecurityPolicy()

        await _run_interceptor(policy, _make_route("https://cdn.example.com/a.js"))
        # Advance past the TTL without sleeping. The real clock is captured
        # first: `security.time` IS the `time` module, so patching its attribute
        # in terms of itself would recurse.
        real_monotonic = time.monotonic
        monkeypatch.setattr(
            "src.infrastructure.browser.security.time.monotonic",
            lambda: real_monotonic() + 3600,
        )
        await _run_interceptor(policy, _make_route("https://cdn.example.com/b.js"))

        assert len(calls) == 2

    def test_cache_evicts_least_recently_used(self):
        """Memory stays bounded whatever a page throws at it."""
        cache = _HostVerdictCache(ttl_seconds=60, max_hosts=2)

        cache.set("a.example", True)
        cache.set("b.example", True)
        cache.get("a.example")  # a becomes the most recent
        cache.set("c.example", True)

        assert cache.get("b.example") is None, "the least recently used host should be evicted"
        assert cache.get("a.example") is True
        assert cache.get("c.example") is True
