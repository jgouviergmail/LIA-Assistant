"""Single source of truth for "who is calling".

Three call sites used to answer this question independently — the global rate
limiter, the GeoIP enrichment and the per-endpoint auth limiter — and all three
read ``scope["client"]``, which uvicorn REWRITES from ``X-Forwarded-For`` under
``--proxy-headers --forwarded-allow-ips "*"``. With every hop trusted, uvicorn
keeps the LEFTMOST entry, and the leftmost entry is the one the visitor supplied:
Cloudflare APPENDS the real address to an existing header rather than replacing
it.

Reproduced in an isolated container on 2026-08-05, replaying the production
topology::

    curl -H "X-Forwarded-For: 127.0.0.1, 198.51.100.42" .../whoami
    -> {"resolved_client": "127.0.0.1"}

So the identity every limiter keys on was chosen by the caller. Rotating it mints
a fresh budget per request, and the audit trail records whatever the caller
claims — the 2600 rate-limit warnings of the 2026-07-30 scan all carry
``geo_country=local`` because the scanner declared itself loopback.

``CF-Connecting-IP`` fixes both: it carries exactly one address and Cloudflare
writes it, overwriting whatever the visitor sent. Trusting it is sound for the
reason the deployment already documents for ``forwarded-allow-ips``: the
published port is loopback-bound (``127.0.0.1:8000:8000``), so the only peers
that can reach uvicorn are cloudflared, the in-container healthcheck and
compose-internal services. Outside that topology the header is simply absent and
the resolution falls back to the peer address, which is what dev already used.

The value is PARSED before it is trusted. An unparsable header is ignored rather
than accepted: a bucket key must never be arbitrary caller-supplied text.
"""

from __future__ import annotations

from ipaddress import ip_address
from typing import Any

#: Returned when neither the trusted header nor a peer address is available.
UNKNOWN_CLIENT_IP = "unknown"

#: Set by Cloudflare on every proxied request, and overwritten if the visitor
#: sends one. Lower-case: ASGI normalises header names.
_TRUSTED_CLIENT_IP_HEADER = b"cf-connecting-ip"


def _headers_of(scope: Any) -> list[tuple[bytes, bytes]]:
    """Raw ASGI headers, tolerating both a scope mapping and a Starlette request.

    Returns an empty list for anything that is not the expected sequence. This
    resolver runs inside the middleware chain, so it must never be the reason a
    request fails: an unreadable scope degrades to the peer address, exactly like
    a missing header.
    """
    if isinstance(scope, dict):
        raw = scope.get("headers")
    else:  # Request-like: .scope carries the same list
        inner = getattr(scope, "scope", None)
        raw = inner.get("headers") if isinstance(inner, dict) else None

    if not isinstance(raw, list | tuple):
        return []

    pairs: list[tuple[bytes, bytes]] = []
    for entry in raw:
        if not isinstance(entry, tuple | list) or len(entry) != 2:
            continue
        name, value = entry
        if isinstance(name, bytes) and isinstance(value, bytes):
            pairs.append((name, value))
    return pairs


def _peer_of(scope: Any) -> str | None:
    """Address uvicorn resolved for the connection, if any."""
    client = scope.get("client") if isinstance(scope, dict) else getattr(scope, "client", None)
    if not client:
        return None
    if isinstance(client, tuple | list):
        return str(client[0]) if client else None
    # Starlette's Address exposes .host
    host = getattr(client, "host", None)
    return str(host) if host else None


def resolve_client_ip(scope: Any) -> str:
    """Return the caller's address, preferring the header the caller cannot write.

    Args:
        scope: An ASGI scope mapping, or any object exposing ``scope``/``client``
            the way a Starlette ``Request`` does.

    Returns:
        The trusted client address, the connection peer when Cloudflare is not in
        front (dev, direct calls), or ``UNKNOWN_CLIENT_IP`` when neither exists.
    """
    for name, value in _headers_of(scope):
        if name.lower() != _TRUSTED_CLIENT_IP_HEADER:
            continue
        candidate = value.decode("latin-1").strip()
        if not candidate:
            break
        try:
            # Parse before trusting: the header feeds rate-limit bucket keys and
            # GeoIP lookups, so arbitrary text must never reach either.
            return str(ip_address(candidate))
        except ValueError:
            break

    return _peer_of(scope) or UNKNOWN_CLIENT_IP
