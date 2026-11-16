"""The instance's own ntfy server (ADR-391): where it is reached and the key LIA holds.

The ``ntfy`` profile of the base Compose file runs the server. LIA publishes on it
from the internal network with a token of its own; people's phones subscribe at its
public address. LIA's account there has no password: its hash is random characters
in bcrypt's shape, which no password matches (the wizard is stdlib-only, without
bcrypt), so the token is the account's only key. Measured on the pinned image: no
password opens the account, a replaced token stops working at the next start.
"""

from __future__ import annotations

import re
import secrets
import string

from scripts.install.addresses import url_host
from scripts.install.model import Exposure, PublicAnswers

#: Where LIA publishes: the ``ntfy`` service on the internal network.
NTFY_INTERNAL_URL = "http://ntfy:80"

#: The host port the service publishes (loopback in the base file, every interface
#: on a LAN install): the port ntfy's documentation runs behind a proxy.
NTFY_HOST_PORT = 2586

#: The relay that wakes iPhones (Apple's push reaches only ntfy.sh's app identity).
#: It receives a message's id and a hash of its topic's address, never its text.
NTFY_IOS_RELAY_URL = "https://ntfy.sh"

_TOKEN_ALPHABET = string.ascii_lowercase + string.digits
_TOKEN_LENGTH = 29
_HASH_ALPHABET = "./" + string.ascii_letters + string.digits
_HASH_LENGTH = 53
_TOKEN = re.compile(rf"tk_[a-z0-9]{{{_TOKEN_LENGTH}}}")
_ACCOUNT_HASH = re.compile(rf"[./A-Za-z0-9]{{{_HASH_LENGTH}}}")


def public_url(public: PublicAnswers) -> str:
    """Where people's phones reach the instance's server, ``""`` when it runs none.

    Args:
        public: The installation's answers.

    Returns:
        The host's published port on a LAN, the server's own name behind a proxy.
    """
    if not public.ntfy_server:
        return ""
    if public.exposure is Exposure.LAN:
        return f"http://{url_host(str(public.server_host))}:{NTFY_HOST_PORT}"
    return f"https://{public.ntfy_domain}"


def is_publish_token(value: str) -> bool:
    """Whether ntfy accepts ``value`` as a declared access token."""
    return _TOKEN.fullmatch(value) is not None


def is_account_hash(value: str) -> bool:
    """Whether ``value`` completes ``$2a$10$`` into a hash ntfy accepts."""
    return _ACCOUNT_HASH.fullmatch(value) is not None


def new_publish_token() -> str:
    """A fresh access token in the shape ntfy declares (``tk_`` and 29 characters)."""
    return "tk_" + "".join(secrets.choice(_TOKEN_ALPHABET) for _ in range(_TOKEN_LENGTH))


def new_account_hash() -> str:
    """Random salt and digest in bcrypt's alphabet: a hash no password matches."""
    return "".join(secrets.choice(_HASH_ALPHABET) for _ in range(_HASH_LENGTH))
