"""Where an installation is reached: one spelling of its addresses (ADR-215).

The environment, the final report and the ntfy server all write an address from
the same answers; one function each, so they never part. An IPv6 host is written
between brackets (RFC 3986), without which its port reads as part of it.
"""

from __future__ import annotations

import ipaddress

from scripts.install.model import Exposure, PublicAnswers

#: The web's port on a LAN install, which the installer's override publishes.
WEB_LAN_PORT = 3000


def url_host(host: str) -> str:
    """``host`` as a URL writes it: an IPv6 literal between brackets.

    Args:
        host: A host name or an IP literal, as the operator answered it.

    Returns:
        The host, bracketed when it is an IPv6 address.
    """
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    return f"[{host}]" if address.version == 6 else host


def web_origin(public: PublicAnswers) -> str:
    """The origin people open: the host's port on a LAN, the web domain otherwise.

    Args:
        public: The installation's answers.

    Returns:
        The origin, with no trailing slash.
    """
    if public.exposure is Exposure.LAN:
        return f"http://{url_host(str(public.server_host))}:{WEB_LAN_PORT}"
    return f"https://{public.web_domain}"
