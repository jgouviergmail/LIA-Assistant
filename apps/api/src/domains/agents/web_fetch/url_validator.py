"""
URL Validation and SSRF Prevention for Web Fetch Tool.

Multi-tenant security module that prevents:
- SSRF attacks via private/internal IP addresses
- Access to cloud metadata endpoints
- Access to internal services via hostname blacklists
- Non-HTTP(S) schemes
- DNS rebinding attacks (resolved before fetch)
- IPv4-mapped IPv6 bypass attacks

Architecture:
    validate_url() is the single async entry point.
    DNS resolution runs via asyncio.to_thread() to avoid blocking the event loop.
    check_ip_safety() is a reusable sync helper for post-redirect validation.
"""

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import structlog

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
    """Immutable result of URL validation."""

    valid: bool
    url: str
    error: str | None = None
    https_upgraded: bool = False


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
    Raises socket.gaierror on DNS failure.
    """
    results = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    return list({result[4][0] for result in results})


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
    )


async def validate_resolved_url(url: str) -> bool:
    """
    Validate a URL after redirect (post-redirect SSRF check).

    Lighter version of validate_url() focused on hostname/IP safety only.
    Used to check response.url after httpx follows redirections.

    Args:
        url: Final URL after redirections

    Returns:
        True if safe, False if blocked
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    # Check hostname blacklist
    if _check_hostname_safety(hostname) is not None:
        return False

    # Check if hostname is a raw IP address
    try:
        ipaddress.ip_address(hostname)
        # It's a raw IP — validate it
        return check_ip_safety(hostname)
    except ValueError:
        pass  # Not a raw IP — resolve DNS below

    # Resolve DNS for domain hostnames
    try:
        resolved_ips = await asyncio.to_thread(_resolve_dns_sync, hostname)
    except socket.gaierror:
        return False

    return all(check_ip_safety(ip_str) for ip_str in resolved_ips)
