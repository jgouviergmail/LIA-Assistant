"""Where the vendor calls this API back, and whether it can (ADR-301).

A live tool (lot 7) and the Live mode's delegation (ADR-301) are both vendor
webhook tools: the vendor's servers POST to a URL of THIS API. That URL is
``TELEPHONY_CALLBACK_BASE_URL`` when the operator declared one (a tunnel on a
development machine), else ``API_URL``. A base whose host is private —
``localhost``, a loopback, a link-local or private range, a ``.local`` or a
Docker alias — can never receive the call: the delegation would time out on
the vendor's side and the person would hear nothing. So the phone's Live mode
is AVAILABLE only when the base is public, and the identity says so with a
stable reason the settings page translates — the choice stays stored, the
effective mode is derived (``PhoneIdentity.call_mode_effective``).
"""

from __future__ import annotations

import ipaddress
import re
from typing import Final
from urllib.parse import urlsplit

from src.core.config import settings

#: Host names and suffixes the vendor's servers cannot resolve to this API.
_PRIVATE_HOSTS: Final[frozenset[str]] = frozenset({"localhost", "host.docker.internal", "api"})
_PRIVATE_SUFFIXES: Final[tuple[str, ...]] = (".local", ".localhost", ".internal", ".lan")

#: An IPv4 address a wildcard DNS name embeds (``192.168.1.20.nip.io``,
#: ``app-10-0-0-4.sslip.io``, ``127.0.0.1.traefik.me``): such a name resolves
#: to that very address, so the vendor reaches exactly what the digits say.
#: Each octet stands between label boundaries — ``v2.example.com`` and a date
#: in a label are not addresses.
_EMBEDDED_IPV4: Final = re.compile(
    r"(?:^|[.-])((?:25[0-5]|2[0-4]\d|1?\d?\d)(?:[.-](?:25[0-5]|2[0-4]\d|1?\d?\d)){3})(?=[.-]|$)"
)
#: The stable code the identity publishes when Live cannot run here.
CALLBACK_NOT_PUBLIC: Final = "callback_not_public"


def callback_base_url() -> str:
    """The base URL the vendor calls back on, without a trailing slash."""
    declared = (settings.telephony_callback_base_url or "").strip()
    return (declared or str(settings.api_url)).rstrip("/")


def is_public_host(host: str) -> bool:
    """Whether a host name could be reached from the vendor's servers.

    Args:
        host: The bare host (no port), as ``urlsplit`` yields it.

    Returns:
        False for the loopback, private, link-local and reserved ranges, for
        an empty host, for the names only this machine or its compose
        network resolves, and for a wildcard DNS name embedding such an
        address; True otherwise.
    """
    name = host.strip().strip("[]").lower()
    if not name or name in _PRIVATE_HOSTS or name.endswith(_PRIVATE_SUFFIXES):
        return False
    literal = _address_of(name)
    if literal is not None:
        return literal.is_global
    if "." not in name:
        return False
    embedded = _EMBEDDED_IPV4.search(name)
    if embedded is None:
        return True
    return ipaddress.ip_address(embedded.group(1).replace("-", ".")).is_global


def _address_of(name: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """The address a bare literal names, or None for a host NAME."""
    try:
        return ipaddress.ip_address(name)
    except ValueError:
        return None


def live_unavailable_reason() -> str | None:
    """Why the phone's Live mode cannot run on this instance, or None when it can."""
    return (
        None
        if is_public_host(urlsplit(callback_base_url()).hostname or "")
        else CALLBACK_NOT_PUBLIC
    )


__all__ = [
    "CALLBACK_NOT_PUBLIC",
    "callback_base_url",
    "is_public_host",
    "live_unavailable_reason",
]
