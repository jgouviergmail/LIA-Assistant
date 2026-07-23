"""Bounded client metadata for device sessions (security program D2, A3).

Deliberately coarse, PII-minimizing extraction: browser/OS FAMILIES (never
the raw user-agent) and TRUNCATED IPs (never the full address — /24 for
IPv4, first 3 hextets for IPv6). The raw values are never stored or logged;
these helpers are the single chokepoint producing what the session payload
may carry (documented reversal of the 2024 minimization decision, ADR-144).
"""

import ipaddress
from dataclasses import dataclass

# Ordered: first match wins (Edge/Opera must precede Chrome; Chrome precedes
# Safari because Chrome's UA contains "Safari").
_BROWSER_FAMILIES: tuple[tuple[str, str], ...] = (
    ("edg", "edge"),
    ("opr", "opera"),
    ("opera", "opera"),
    ("firefox", "firefox"),
    ("chrome", "chrome"),
    ("crios", "chrome"),
    ("safari", "safari"),
)

_OS_FAMILIES: tuple[tuple[str, str], ...] = (
    ("android", "android"),
    ("iphone", "ios"),
    ("ipad", "ios"),
    ("windows", "windows"),
    ("mac os", "macos"),
    ("macintosh", "macos"),
    ("linux", "linux"),
)

UNKNOWN_FAMILY = "unknown"


@dataclass(frozen=True)
class SessionClientMeta:
    """Bounded per-session client metadata (the ONLY shape sessions may carry)."""

    ua_family: str
    os_family: str
    ip_trunc: str


def extract_client_meta(user_agent: str | None, client_ip: str | None) -> SessionClientMeta:
    """Build the bounded metadata a new session may store.

    Args:
        user_agent: Raw User-Agent header (never stored as-is).
        client_ip: Raw client IP (never stored as-is).

    Returns:
        Coarse families + truncated IP.
    """
    ua_family, os_family = parse_user_agent(user_agent)
    return SessionClientMeta(
        ua_family=ua_family,
        os_family=os_family,
        ip_trunc=truncate_ip(client_ip),
    )


def parse_user_agent(user_agent: str | None) -> tuple[str, str]:
    """Reduce a raw user-agent to coarse (browser_family, os_family).

    Args:
        user_agent: Raw User-Agent header, or None.

    Returns:
        Tuple of lowercase family labels; ``unknown`` when unrecognized.
    """
    if not user_agent:
        return UNKNOWN_FAMILY, UNKNOWN_FAMILY

    lowered = user_agent.lower()
    browser = next(
        (family for needle, family in _BROWSER_FAMILIES if needle in lowered),
        UNKNOWN_FAMILY,
    )
    os_family = next(
        (family for needle, family in _OS_FAMILIES if needle in lowered),
        UNKNOWN_FAMILY,
    )
    return browser, os_family


def truncate_ip(ip: str | None) -> str:
    """Truncate an IP for display without identifying the exact host.

    IPv4 keeps the /24 (`192.168.1.x`); IPv6 keeps the first 3 hextets
    (`2001:db8:85a3:…`). Unparsable input collapses to ``unknown``.

    Args:
        ip: Raw client IP, or None.

    Returns:
        The truncated display form — never the full address.
    """
    if not ip:
        return UNKNOWN_FAMILY
    try:
        parsed = ipaddress.ip_address(ip)
    except ValueError:
        return UNKNOWN_FAMILY

    if isinstance(parsed, ipaddress.IPv4Address):
        octets = str(parsed).split(".")
        return f"{octets[0]}.{octets[1]}.{octets[2]}.x"

    hextets = parsed.exploded.split(":")
    return f"{hextets[0]}:{hextets[1]}:{hextets[2]}:…"
