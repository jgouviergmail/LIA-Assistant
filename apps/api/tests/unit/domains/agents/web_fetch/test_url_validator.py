"""
Unit tests for URL Validator (SSRF Prevention).

Tests cover:
- Valid public URLs (HTTPS)
- HTTP → HTTPS automatic upgrade
- Blocked private IP ranges (RFC 1918, RFC 6598 CGNAT, loopback, link-local, metadata)
- Blocked reserved ranges (test-nets, benchmarking, multicast, future-reserved)
- IPv4-mapped IPv6 bypass prevention (::ffff:127.0.0.1)
- Blocked IPv6 addresses (loopback, ULA, link-local)
- Blocked hostnames (localhost, metadata endpoints, internal suffixes)
- Invalid schemes (ftp, file, javascript, no scheme)
- Edge cases (empty URL, malformed URL, no hostname)
- DNS resolution mocking
- check_ip_safety() reusable helper
- the verdict carries the addresses it validated, and a pinned request uses them
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.domains.agents.web_fetch.url_validator import (
    UrlValidationResult,
    check_ip_safety,
    pinned_request_parts,
    pinned_stream,
    validate_url,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture()
def mock_dns_public():
    """Mock DNS resolution returning a public IP."""
    with patch(
        "src.domains.agents.web_fetch.url_validator.asyncio.to_thread",
        new_callable=AsyncMock,
        return_value=["93.184.216.34"],
    ) as mock:
        yield mock


@pytest.fixture()
def mock_dns_private():
    """Mock DNS resolution returning a private IP (SSRF attack)."""
    with patch(
        "src.domains.agents.web_fetch.url_validator.asyncio.to_thread",
        new_callable=AsyncMock,
        return_value=["192.168.1.1"],
    ) as mock:
        yield mock


@pytest.fixture()
def mock_dns_failure():
    """Mock DNS resolution failure."""
    import socket

    with patch(
        "src.domains.agents.web_fetch.url_validator.asyncio.to_thread",
        new_callable=AsyncMock,
        side_effect=socket.gaierror("DNS resolution failed"),
    ) as mock:
        yield mock


# ============================================================================
# check_ip_safety() TESTS
# ============================================================================


class TestCheckIpSafety:
    """Tests for the reusable check_ip_safety() helper."""

    @pytest.mark.parametrize(
        "ip",
        [
            "93.184.216.34",  # Public IPv4
            "8.8.8.8",  # Google DNS
            "1.1.1.1",  # Cloudflare DNS
            "2606:4700::1",  # Public IPv6
            "104.16.132.229",  # Cloudflare (not in CGNAT range)
        ],
    )
    def test_public_ips_are_safe(self, ip: str):
        assert check_ip_safety(ip) is True

    @pytest.mark.parametrize(
        ("ip", "description"),
        [
            # RFC 1918 private
            ("10.0.0.1", "RFC 1918 class A"),
            ("10.255.255.255", "RFC 1918 class A boundary"),
            ("172.16.0.1", "RFC 1918 class B"),
            ("172.31.255.255", "RFC 1918 class B boundary"),
            ("192.168.0.1", "RFC 1918 class C"),
            ("192.168.255.255", "RFC 1918 class C boundary"),
            # Loopback
            ("127.0.0.1", "Loopback"),
            ("127.255.255.255", "Loopback boundary"),
            # Link-local / metadata
            ("169.254.169.254", "AWS/GCP metadata"),
            ("169.254.0.1", "Link-local"),
            # Unspecified
            ("0.0.0.0", "Unspecified"),
            ("0.1.2.3", "0.0.0.0/8 range"),
            # CGNAT (RFC 6598)
            ("100.64.0.1", "CGNAT start"),
            ("100.127.255.254", "CGNAT end"),
            # Benchmarking (RFC 2544)
            ("198.18.0.1", "Benchmarking start"),
            ("198.19.255.254", "Benchmarking end"),
            # Test-Nets (RFC 5737)
            ("192.0.2.1", "TEST-NET-1"),
            ("198.51.100.1", "TEST-NET-2"),
            ("203.0.113.1", "TEST-NET-3"),
            # Reserved for future use
            ("240.0.0.1", "Reserved future"),
            ("255.255.255.254", "Reserved future boundary"),
            # Multicast
            ("224.0.0.1", "Multicast start"),
            ("239.255.255.255", "Multicast end"),
        ],
    )
    def test_private_ipv4_are_blocked(self, ip: str, description: str):
        assert check_ip_safety(ip) is False, f"Expected {ip} ({description}) to be blocked"

    @pytest.mark.parametrize(
        ("ip", "description"),
        [
            ("::1", "IPv6 loopback"),
            ("fc00::1", "IPv6 ULA"),
            ("fd12:3456:789a::1", "IPv6 ULA (fd prefix)"),
            ("fe80::1", "IPv6 link-local"),
        ],
    )
    def test_private_ipv6_are_blocked(self, ip: str, description: str):
        assert check_ip_safety(ip) is False, f"Expected {ip} ({description}) to be blocked"

    # --- IPv4-mapped IPv6 bypass prevention ---

    @pytest.mark.parametrize(
        ("ip", "description"),
        [
            ("::ffff:127.0.0.1", "IPv4-mapped loopback"),
            ("::ffff:10.0.0.1", "IPv4-mapped RFC 1918 class A"),
            ("::ffff:192.168.1.1", "IPv4-mapped RFC 1918 class C"),
            ("::ffff:169.254.169.254", "IPv4-mapped metadata"),
            ("::ffff:100.64.0.1", "IPv4-mapped CGNAT"),
        ],
    )
    def test_ipv4_mapped_ipv6_are_blocked(self, ip: str, description: str):
        assert (
            check_ip_safety(ip) is False
        ), f"Expected {ip} ({description}) to be blocked (IPv4-mapped IPv6 bypass)"

    def test_ipv4_mapped_ipv6_public_is_safe(self):
        # ::ffff:8.8.8.8 is a public IP mapped as IPv6 — should be safe
        assert check_ip_safety("::ffff:8.8.8.8") is True

    def test_invalid_ip_returns_false(self):
        assert check_ip_safety("not-an-ip") is False

    def test_empty_ip_returns_false(self):
        assert check_ip_safety("") is False


# ============================================================================
# validate_url() TESTS
# ============================================================================


class TestValidateUrl:
    """Tests for the main async URL validation entry point."""

    async def test_valid_https_url(self, mock_dns_public):
        result = await validate_url("https://example.com/article")
        assert result.valid is True
        assert result.url == "https://example.com/article"
        assert result.error is None
        assert result.https_upgraded is False

    async def test_http_upgraded_to_https(self, mock_dns_public):
        result = await validate_url("http://example.com/page")
        assert result.valid is True
        assert result.url == "https://example.com/page"
        assert result.https_upgraded is True

    async def test_preserves_path_and_query(self, mock_dns_public):
        url = "https://example.com/path/to/page?q=test&lang=fr#section"
        result = await validate_url(url)
        assert result.valid is True
        assert result.url == url

    async def test_strips_whitespace(self, mock_dns_public):
        result = await validate_url("  https://example.com  ")
        assert result.valid is True
        assert result.url == "https://example.com"

    # --- Blocked schemes ---

    @pytest.mark.parametrize(
        "url",
        [
            "ftp://example.com/file",
            "file:///etc/passwd",
            "javascript:alert(1)",
            "data:text/html,<h1>test</h1>",
            "gopher://example.com",
        ],
    )
    async def test_invalid_schemes_rejected(self, url: str):
        result = await validate_url(url)
        assert result.valid is False
        assert "Unsupported scheme" in result.error

    async def test_no_scheme_rejected(self):
        result = await validate_url("example.com/page")
        assert result.valid is False

    # --- Blocked hostnames ---

    @pytest.mark.parametrize(
        "url",
        [
            "https://localhost/admin",
            "https://LOCALHOST/admin",  # Case insensitive
            "https://metadata.google.internal/computeMetadata/v1/",
            "https://metadata.google/",
            "https://169.254.169.254/latest/meta-data/",
        ],
    )
    async def test_blocked_hostnames_rejected(self, url: str):
        result = await validate_url(url)
        assert result.valid is False
        assert "Blocked" in result.error

    @pytest.mark.parametrize(
        "url",
        [
            "https://api.internal/v1/",
            "https://service.local/",
            "https://server.localhost/",
        ],
    )
    async def test_blocked_hostname_suffixes_rejected(self, url: str):
        result = await validate_url(url)
        assert result.valid is False
        assert "Blocked hostname suffix" in result.error

    # --- Blocked raw IPs ---

    @pytest.mark.parametrize(
        "url",
        [
            "https://10.0.0.1/secret",
            "https://172.16.0.1/internal",
            "https://192.168.1.1/admin",
            "https://127.0.0.1:8080/",
            "https://[::1]/admin",
            # New ranges
            "https://100.64.0.1/cgnat",
            "https://198.18.0.1/benchmark",
            "https://192.0.2.1/testnet1",
            "https://240.0.0.1/reserved",
        ],
    )
    async def test_raw_private_ips_rejected(self, url: str):
        result = await validate_url(url)
        assert result.valid is False
        assert "Blocked IP" in result.error

    # --- IPv4-mapped IPv6 in URLs ---

    async def test_ipv4_mapped_ipv6_loopback_rejected(self):
        result = await validate_url("https://[::ffff:127.0.0.1]/admin")
        assert result.valid is False
        assert "Blocked IP" in result.error

    # --- DNS resolution to private IP ---

    async def test_dns_resolving_to_private_ip_blocked(self, mock_dns_private):
        result = await validate_url("https://evil-redirect.attacker.com")
        assert result.valid is False
        assert "resolves to blocked IP" in result.error

    async def test_dns_failure_rejected(self, mock_dns_failure):
        result = await validate_url("https://nonexistent.invalid")
        assert result.valid is False
        assert "DNS resolution failed" in result.error

    async def test_a_hostname_no_resolver_can_encode_is_a_verdict(self):
        # A label past 63 characters fails IDNA encoding inside getaddrinfo — a
        # UnicodeError raised before any network — and must read as a refusal.
        result = await validate_url("https://" + "a" * 70 + ".example.org/")
        assert result.valid is False
        assert "DNS resolution failed" in result.error

    # --- Empty/malformed URLs ---

    async def test_empty_url_rejected(self):
        result = await validate_url("")
        assert result.valid is False
        assert "Empty" in result.error

    async def test_whitespace_only_rejected(self):
        result = await validate_url("   ")
        assert result.valid is False
        assert "Empty" in result.error

    async def test_no_hostname_rejected(self):
        result = await validate_url("https:///path/only")
        assert result.valid is False
        assert "hostname" in result.error.lower()

    # --- Result type ---

    async def test_result_is_frozen_dataclass(self, mock_dns_public):
        result = await validate_url("https://example.com")
        assert isinstance(result, UrlValidationResult)
        with pytest.raises(AttributeError):
            result.valid = False  # type: ignore[misc]


# ============================================================================
# THE VERDICT CARRIES ITS ADDRESSES, AND A REQUEST IS PINNED TO THEM (ADR-326)
# ============================================================================


class TestVerdictAddresses:
    """A valid verdict names what it validated; a refusal names nothing."""

    async def test_a_name_carries_what_it_resolved_to(self, mock_dns_public):
        result = await validate_url("https://example.com/page")
        assert result.valid is True
        assert result.resolved_ips == ("93.184.216.34",)

    async def test_a_raw_address_carries_itself(self):
        result = await validate_url("https://93.184.216.34/page")
        assert result.valid is True
        assert result.resolved_ips == ("93.184.216.34",)

    async def test_a_refusal_carries_no_address(self, mock_dns_private):
        result = await validate_url("https://evil.attacker.com/page")
        assert result.valid is False
        assert result.resolved_ips == ()


class TestPinnedRequest:
    """The request goes where the check looked; the name stays in Host and the SNI."""

    def test_the_url_host_is_the_validated_address(self):
        verdict = UrlValidationResult(
            valid=True, url="https://example.com:8443/a?b=1", resolved_ips=("93.184.216.34",)
        )
        url, headers, extensions = pinned_request_parts(verdict)
        assert str(url) == "https://93.184.216.34:8443/a?b=1"
        assert headers == {"Host": "example.com:8443"}
        assert extensions == {"sni_hostname": "example.com"}

    def test_a_default_port_leaves_host_bare_and_http_sets_no_sni(self):
        verdict = UrlValidationResult(
            valid=True, url="http://example.com/a", resolved_ips=("93.184.216.34",)
        )
        url, headers, extensions = pinned_request_parts(verdict)
        assert str(url) == "http://93.184.216.34/a"
        assert headers == {"Host": "example.com"}
        assert extensions == {}

    def test_an_ipv6_address_is_bracketed(self):
        verdict = UrlValidationResult(
            valid=True,
            url="https://example.com/a",
            resolved_ips=("2606:2800:220:1:248:1893:25c8:1946",),
        )
        url, _headers, _extensions = pinned_request_parts(verdict)
        assert url.host == "2606:2800:220:1:248:1893:25c8:1946"
        assert str(url).startswith("https://[2606:2800:220:1:248:1893:25c8:1946]/a")

    def test_an_internationalised_name_travels_in_its_wire_form(self):
        # `URL.host` decodes the IDNA name; a header is ASCII, so sending the
        # decoded spelling raised UnicodeEncodeError where the plain URL had
        # always worked (the client encodes it itself). Regression found by
        # the cold review of ADR-326.
        verdict = UrlValidationResult(
            valid=True, url="https://bücher.example:8443/p?q=1", resolved_ips=("93.184.216.34",)
        )
        url, headers, extensions = pinned_request_parts(verdict)
        assert str(url) == "https://93.184.216.34:8443/p?q=1"
        assert headers == {"Host": "xn--bcher-kva.example:8443"}
        assert extensions == {"sni_hostname": "xn--bcher-kva.example"}
        # And the request builds: this is where the decoded form used to raise.
        httpx.Request("GET", url, headers=headers, extensions=extensions)

    @pytest.mark.parametrize(
        "verdict",
        [
            UrlValidationResult(valid=False, url="https://example.com/", error="blocked"),
            UrlValidationResult(valid=True, url="https://example.com/"),
        ],
        ids=["a refusal", "a valid verdict that validated no address"],
    )
    def test_a_verdict_without_an_address_is_refused(self, verdict):
        with pytest.raises(ValueError, match="carries an address"):
            pinned_request_parts(verdict)

    async def test_a_callers_host_header_never_unpins_the_request(self):
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, content=b"ok")

        verdict = UrlValidationResult(
            valid=True, url="https://example.com/page", resolved_ips=("93.184.216.34",)
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            async with pinned_stream(
                client, "GET", verdict, headers={"host": "evil.example", "X-Probe": "1"}
            ) as response:
                assert response.status_code == 200
        (request,) = seen
        assert request.headers.get_list("host") == ["example.com"]
        assert request.headers["x-probe"] == "1"

    async def test_the_stream_connects_to_the_address_with_the_name_in_host(self):
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, content=b"ok")

        verdict = UrlValidationResult(
            valid=True, url="https://example.com/page", resolved_ips=("93.184.216.34",)
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            async with pinned_stream(
                client, "GET", verdict, headers={"User-Agent": "probe"}
            ) as response:
                assert response.status_code == 200
        (request,) = seen
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "example.com"
        assert request.headers["user-agent"] == "probe"
        assert request.extensions["sni_hostname"] == "example.com"

    async def test_the_stream_never_follows_a_redirect_itself(self):
        hops: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            hops.append(str(request.url))
            return httpx.Response(302, headers={"location": "https://evil.example/"})

        verdict = UrlValidationResult(
            valid=True, url="https://example.com/page", resolved_ips=("93.184.216.34",)
        )
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), follow_redirects=True
        ) as client:
            async with pinned_stream(client, "GET", verdict) as response:
                assert response.status_code == 302
        assert hops == ["https://93.184.216.34/page"]
