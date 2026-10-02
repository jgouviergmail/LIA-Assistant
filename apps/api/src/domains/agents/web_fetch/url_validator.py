"""
URL Validation and SSRF Prevention for Web Fetch Tool.

Multi-tenant security module that prevents:
- SSRF attacks via private/internal IP addresses
- Access to cloud metadata endpoints
- Access to internal services via hostname blacklists
- Non-HTTP(S) schemes
- DNS rebinding attacks: the request connects to the address the check saw
- IPv4-mapped IPv6 bypass attacks

Architecture (ADR-326):
    validate_url() is the single async entry point; its verdict carries the
    addresses it validated. pinned_stream() is the ONE way a validated URL is
    requested: connected to a validated address, the name kept in ``Host`` and
    the SNI, redirects never followed — a redirect is a new URL the caller
    validates and requests again, so every hop is checked BEFORE it is
    contacted. The former shape (validate, then let the client follow
    redirects and re-resolve the name, then check where it ended up) was
    measured to contact a cloud metadata address on a redirect and to hand an
    internal page back under a rebinding name.
    DNS resolution runs via asyncio.to_thread() to avoid blocking the event loop.
    check_ip_safety() is the reusable sync predicate over one address.
"""

import asyncio
import ipaddress
import socket
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

from src.infrastructure.utils.bounded_read import ACCEPT_ENCODING_HEADER

logger = structlog.get_logger(__name__)

# ============================================================================
# BLOCKED NETWORK RANGES
# RFC 1918 + RFC 6598 + loopback + link-local + metadata + ULA + reserved
# ============================================================================

_BLOCKED_IP_NETWORKS = [
    # IPv4 private (RFC 1918)
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    # IPv4 loopback
    ipaddress.ip_network("127.0.0.0/8"),
    # IPv4 link-local + AWS/GCP metadata
    ipaddress.ip_network("169.254.0.0/16"),
    # IPv4 "this" network
    ipaddress.ip_network("0.0.0.0/8"),
    # IPv4 CGNAT / Shared Address Space (RFC 6598)
    ipaddress.ip_network("100.64.0.0/10"),
    # IPv4 benchmarking (RFC 2544)
    ipaddress.ip_network("198.18.0.0/15"),
    # IPv4 documentation / test-nets (RFC 5737)
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    # IPv4 reserved for future use
    ipaddress.ip_network("240.0.0.0/4"),
    # IPv4 multicast
    ipaddress.ip_network("224.0.0.0/4"),
    # IPv6 loopback
    ipaddress.ip_network("::1/128"),
    # IPv6 ULA (Unique Local Address)
    ipaddress.ip_network("fc00::/7"),
    # IPv6 link-local
    ipaddress.ip_network("fe80::/10"),
]

# ============================================================================
# BLOCKED HOSTNAMES (case-insensitive)
# ============================================================================

_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "metadata.google",
        "169.254.169.254",  # AWS/GCP metadata endpoint
    }
)

_BLOCKED_HOSTNAME_SUFFIXES = (
    ".internal",
    ".local",
    ".localhost",
)

# ============================================================================
# ALLOWED SCHEMES
# ============================================================================

_ALLOWED_SCHEMES = frozenset({"http", "https"})


@dataclass(frozen=True)
class UrlValidationResult:
    """Immutable result of URL validation.

    ``resolved_ips`` are the addresses the verdict validated — the raw IP of
    the URL, or what the name resolved to at check time. A request made on the
    verdict connects to ONE of them (:func:`pinned_stream`), never to a fresh
    resolution of the name: a name that answers a public address at check
    time and a private one at connect time (DNS rebinding) was measured to hand
    an internal page back to the tool (ADR-326). A valid verdict always carries
    at least one; a refusal carries none.
    """

    valid: bool
    url: str
    error: str | None = None
    https_upgraded: bool = False
    resolved_ips: tuple[str, ...] = ()


def _normalize_ip(
    addr: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """
    Normalize IP address, extracting IPv4 from IPv4-mapped IPv6 addresses.

    Prevents bypass via ::ffff:127.0.0.1 (IPv4-mapped IPv6) which would
    otherwise evade IPv4 blocklist checks.
    """
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        return addr.ipv4_mapped
    return addr


def check_ip_safety(ip_str: str) -> bool:
    """
    Check if an IP address is safe (not in blocked ranges).

    Reusable helper for both pre-fetch DNS validation and post-redirect checks.
    Handles IPv4-mapped IPv6 addresses (e.g., ::ffff:127.0.0.1 → 127.0.0.1).

    Args:
        ip_str: IP address string (IPv4 or IPv6)

    Returns:
        True if the IP is safe (public), False if blocked (private/internal)
    """
    try:
        addr = _normalize_ip(ipaddress.ip_address(ip_str))
    except ValueError:
        return False

    return not any(addr in network for network in _BLOCKED_IP_NETWORKS)


def _check_hostname_safety(hostname: str) -> str | None:
    """
    Check hostname against blacklists.

    Returns None if safe, error message if blocked.
    """
    hostname_lower = hostname.lower()

    if hostname_lower in _BLOCKED_HOSTNAMES:
        return f"Blocked hostname: {hostname}"

    if any(hostname_lower.endswith(suffix) for suffix in _BLOCKED_HOSTNAME_SUFFIXES):
        return f"Blocked hostname suffix: {hostname}"

    return None


def _resolve_dns_sync(hostname: str) -> list[str]:
    """
    Resolve hostname to IP addresses (synchronous, run via asyncio.to_thread).

    Returns list of resolved IP strings.
    Raises socket.gaierror on DNS failure — including a hostname no IDNA
    encoder accepts (a label past 63 characters), which getaddrinfo reports
    as a UnicodeError before asking any resolver: the callers' contract is
    a verdict, never an exception.
    """
    try:
        results = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except UnicodeError as exc:
        raise socket.gaierror(socket.EAI_NONAME, "hostname cannot be encoded") from exc
    # sockaddr[0] is typed str | int (typeshed widens for non-IP families); for
    # AF_INET/AF_INET6 it is always the IP string — keep only those.
    ips: set[str] = set()
    for result in results:
        host = result[4][0]
        if isinstance(host, str):
            ips.add(host)
    return list(ips)


async def validate_url(url: str) -> UrlValidationResult:
    """
    Validate a URL for safety (SSRF prevention) and normalize it.

    Steps:
        1. Parse URL and validate scheme (HTTP/HTTPS only)
        2. Check hostname against blacklists
        3. Resolve DNS (async, non-blocking) and check IPs against blocked ranges
        4. Upgrade HTTP to HTTPS

    Args:
        url: Raw URL from user/LLM

    Returns:
        UrlValidationResult with valid=True and sanitized URL, or valid=False with error
    """
    if not url or not url.strip():
        return UrlValidationResult(valid=False, url="", error="Empty URL")

    url = url.strip()

    # 1. Parse URL
    try:
        parsed = urlparse(url)
    except Exception:
        return UrlValidationResult(valid=False, url=url, error="Malformed URL")

    # 2. Validate scheme
    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        return UrlValidationResult(
            valid=False,
            url=url,
            error=f"Unsupported scheme: {scheme or 'none'}. Only HTTP/HTTPS allowed",
        )

    # 3. Validate hostname exists
    hostname = parsed.hostname
    if not hostname:
        return UrlValidationResult(valid=False, url=url, error="No hostname in URL")

    # 4. Check hostname blacklist
    hostname_error = _check_hostname_safety(hostname)
    if hostname_error:
        return UrlValidationResult(valid=False, url=url, error=hostname_error)

    # 5. Check if hostname is a raw IP address
    try:
        ip_addr = ipaddress.ip_address(hostname)
        if not check_ip_safety(str(ip_addr)):
            return UrlValidationResult(
                valid=False,
                url=url,
                error=f"Blocked IP address: {hostname}",
            )
        # Raw IP, skip DNS resolution
        resolved_ips = [str(ip_addr)]
    except ValueError:
        # Not a raw IP — resolve DNS
        try:
            resolved_ips = await asyncio.to_thread(_resolve_dns_sync, hostname)
        except socket.gaierror:
            return UrlValidationResult(
                valid=False,
                url=url,
                error=f"DNS resolution failed for: {hostname}",
            )

        # 6. Check resolved IPs against blocked ranges
        for ip_str in resolved_ips:
            if not check_ip_safety(ip_str):
                logger.warning(
                    "ssrf_blocked_dns",
                    hostname=hostname,
                    resolved_ip=ip_str,
                )
                return UrlValidationResult(
                    valid=False,
                    url=url,
                    error=f"Hostname {hostname} resolves to blocked IP: {ip_str}",
                )

    # 7. Upgrade HTTP → HTTPS
    https_upgraded = False
    safe_url = url
    if scheme == "http":
        safe_url = "https" + url[4:]
        https_upgraded = True

    return UrlValidationResult(
        valid=True,
        url=safe_url,
        https_upgraded=https_upgraded,
        resolved_ips=tuple(resolved_ips),
    )


def pinned_request_parts(
    verdict: UrlValidationResult,
) -> tuple[httpx.URL, dict[str, str], dict[str, Any]]:
    """What a request made on a verdict is built from: its URL, headers, extensions.

    The URL's host is the FIRST address the verdict validated, so the connection
    goes where the check looked; the ``Host`` header and, over TLS, the SNI
    carry the name, so the server answers for the right site and the
    certificate is verified against the name, never the address. The name is
    the WIRE form (``raw_host``, IDNA-encoded): a header is ASCII, and
    ``URL.host`` of an internationalised name is its decoded spelling — sent as
    a header it raised ``UnicodeEncodeError`` where the plain URL, encoded by
    the client itself, had always worked. :func:`pinned_stream` keeps these two
    headers OVER a caller's own.

    Args:
        verdict: A VALID verdict of :func:`validate_url`.

    Returns:
        ``(url, headers, extensions)`` for ``client.stream`` / ``client.request``.

    Raises:
        ValueError: The verdict is a refusal, or validated no address.
    """
    if not verdict.valid or not verdict.resolved_ips:
        raise ValueError("a request is made on a valid verdict that carries an address")
    logical = httpx.URL(verdict.url)
    pinned = logical.copy_with(host=verdict.resolved_ips[0])
    wire_name = logical.raw_host.decode("ascii")
    host_header = wire_name
    if logical.port is not None:
        host_header = f"{host_header}:{logical.port}"
    headers = {"Host": host_header}
    extensions: dict[str, Any] = {}
    if logical.scheme == "https":
        extensions["sni_hostname"] = wire_name
    return pinned, headers, extensions


def pinned_stream(
    client: httpx.AsyncClient,
    method: str,
    verdict: UrlValidationResult,
    *,
    headers: dict[str, str] | None = None,
    timeout: float | httpx.Timeout | None = None,
) -> AbstractAsyncContextManager[httpx.Response]:
    """Open a streaming request on a verdict, connected to the address it validated.

    The ONE way a validated URL is requested (ADR-326): redirects are never
    followed here — a redirect is a new URL, which the caller validates and
    requests through this function again, so every hop is checked BEFORE it is
    contacted and connects to the address that was checked.

    Args:
        client: The caller's client.
        method: The HTTP method.
        verdict: A valid verdict of :func:`validate_url`.
        headers: The caller's headers. The pinning ``Host`` wins over any
            ``host`` they carry, whatever its case: a request that could be
            unpinned by a header would not be pinned. Without an
            ``Accept-Encoding`` of theirs, the request offers exactly the
            codings ``read_bounded`` decodes under its ceiling — never the
            client's default, which grows with whatever decoder is installed.
        timeout: The request timeout, the client's when None.

    Returns:
        The response context manager ``client.stream`` hands back.
    """
    url, pin_headers, extensions = pinned_request_parts(verdict)
    caller_headers = {k: v for k, v in (headers or {}).items() if k.lower() != "host"}
    if not any(name.lower() == "accept-encoding" for name in caller_headers):
        caller_headers["Accept-Encoding"] = ACCEPT_ENCODING_HEADER
    request_kwargs: dict[str, Any] = {
        "headers": {**caller_headers, **pin_headers},
        "extensions": extensions,
        "follow_redirects": False,
    }
    if timeout is not None:
        request_kwargs["timeout"] = timeout
    return client.stream(method, url, **request_kwargs)
