"""What LIA sends to an ntfy server, and what it accepts from a person (ADR-391).

ntfy delivers a notification to every app subscribed to a TOPIC, and the topic is the only secret:
whoever knows it reads what is published to it. So:

- a topic LIA owns is drawn from a strong random source (:func:`new_topic`), under a prefix the
  instance server's access list grants LIA alone the right to publish to;
- what a person types — a topic, an access token, a server — is refused here, before any
  request, when ntfy itself would refuse it or when it would take LIA somewhere it must not go;
- a person's words leave only when the person chose to (minimal content by default, owner
  decision 2026-11-16), and never more than the push shows: a notification kept in LIA
  (``NotificationPrivacy.IN_APP_SENSITIVE``) leaves as the push leaves it, through the one door
  that decides it (``notification_preview``).
"""

from __future__ import annotations

import re
import secrets
import string
from enum import StrEnum
from typing import Final
from urllib.parse import quote, urlencode, urlsplit

from src.core.constants import (
    NTFY_MESSAGE_MAX_BYTES,
    NTFY_SUBSCRIBE_DISPLAY_NAME,
    NTFY_TITLE_MAX_BYTES,
    NTFY_TOPIC_PREFIX,
    NTFY_TOPIC_RANDOM_CHARS,
)
from src.core.notification_privacy import NotificationPrivacy, notification_preview
from src.domains.notifications.ntfy_errors import (
    SERVER_URL_INVALID,
    SERVER_URL_NOT_HTTPS,
    SERVER_URL_REFUSED,
    TOKEN_INVALID,
    TOPIC_INVALID,
)
from src.infrastructure.utils.url_validation import literal_refusal


class NtfyContent(StrEnum):
    """What a publication carries: a notice that LIA has something, or the words themselves."""

    MINIMAL = "minimal"
    FULL = "full"


class NtfyServerKind(StrEnum):
    """Whose server a subscription lives on: the instance's, or one the person chose."""

    INSTANCE = "instance"
    CUSTOM = "custom"


#: ntfy's own rule for a topic name.
_TOPIC: Final = re.compile(r"[-_A-Za-z0-9]{1,64}")
#: ntfy's access tokens: « tk_ » and 29 characters, 32 in all.
_TOKEN: Final = re.compile(r"tk_[A-Za-z0-9]{29}")
_ALPHABET: Final = string.ascii_letters + string.digits
_ELLIPSIS: Final = "…"


def new_topic() -> str:
    """A topic LIA owns: its prefix, then an unguessable suffix."""
    suffix = "".join(secrets.choice(_ALPHABET) for _ in range(NTFY_TOPIC_RANDOM_CHARS))
    return NTFY_TOPIC_PREFIX + suffix


def topic_refusal(topic: str) -> str | None:
    """Why ntfy would refuse a topic a person typed, or None."""
    return None if _TOPIC.fullmatch(topic) else TOPIC_INVALID


def token_refusal(token: str) -> str | None:
    """Why an access token a person typed is not one ntfy issues, or None."""
    return None if _TOKEN.fullmatch(token) else TOKEN_INVALID


def server_url_refusal(url: str) -> str | None:
    """Why LIA refuses a server a person typed, or None.

    A person's server is reached on the public network, over TLS, with no credential in its
    address — the token travels in a header. Where its name resolves is checked again before
    every request (``NtfyClient.publish_checked``): passing here proves only the spelling.

    An address is read as the client will read it, or refused: ``urlsplit`` silently drops a
    line break (« ntfy.sh⏎.evil.test » would read as the host ``ntfy.sh.evil.test``), so no
    space or control character is accepted at all, and a port no socket can use is refused.

    Args:
        url: The server's address, as the person typed it.

    Returns:
        A refusal code, or None.
    """
    text = url.strip()
    if any(character.isspace() or not character.isprintable() for character in text):
        return SERVER_URL_INVALID
    try:
        parts = urlsplit(text)
        hostname, port = parts.hostname, parts.port
    except ValueError:
        return SERVER_URL_INVALID
    if parts.scheme != "https" or not hostname:
        return SERVER_URL_NOT_HTTPS
    if port == 0 or parts.username or parts.password or parts.query or parts.fragment:
        return SERVER_URL_INVALID
    if literal_refusal(text) is not None:
        return SERVER_URL_REFUSED
    return None


def subscribe_link(server_url: str, topic: str) -> str | None:
    """The ``ntfy://`` link that subscribes the ntfy app to a topic in one tap.

    The app reads ``ntfy://<host>/<topic>`` and nothing else: a server under a path is
    subscribed by hand. A server in clear (a LAN install) says so (``secure=false``).

    Args:
        server_url: The server's address as an app reaches it.
        topic: The topic.

    Returns:
        The link, or None when the address cannot be named that way.
    """
    try:
        parts = urlsplit(server_url.strip())
        host = parts.netloc if parts.hostname else ""
    except ValueError:
        return None
    if parts.scheme not in ("https", "http") or not host or parts.path.strip("/"):
        return None
    query = urlencode(
        {"display": NTFY_SUBSCRIBE_DISPLAY_NAME}
        | ({"secure": "false"} if parts.scheme == "http" else {})
    )
    return f"ntfy://{host}/{quote(topic, safe='')}?{query}"


def _fit(text: str, max_bytes: int) -> str:
    """Text within a byte budget, cut on a character and marked when cut."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    room = max_bytes - len(_ELLIPSIS.encode("utf-8"))
    return encoded[:room].decode("utf-8", errors="ignore").rstrip() + _ELLIPSIS


def publication(
    *,
    topic: str,
    title: str,
    body: str,
    click: str,
    content: NtfyContent,
    language: str,
    privacy: NotificationPrivacy,
) -> dict[str, str]:
    """The JSON publication of one notification on one topic.

    Args:
        topic: The subscription's topic.
        title: The notification's title, as the push shows it.
        body: Its words, as the push shows them (plain text).
        click: The absolute address the notification opens.
        content: What the person chose to receive.
        language: The person's language, for the minimal notice.
        privacy: Whether the notification is kept in LIA.

    Returns:
        ntfy's JSON fields: topic, title, message, click.
    """
    if content is NtfyContent.MINIMAL:
        privacy = NotificationPrivacy.IN_APP_SENSITIVE
    shown_title, shown_body = notification_preview(privacy, language, title, body)
    # ntfy writes « triggered » for an empty message: the title stands in.
    message = shown_body.strip() or shown_title
    return {
        "topic": topic,
        "title": _fit(shown_title, NTFY_TITLE_MAX_BYTES),
        "message": _fit(message, NTFY_MESSAGE_MAX_BYTES),
        "click": click,
    }


__all__ = [
    "NtfyContent",
    "NtfyServerKind",
    "new_topic",
    "publication",
    "server_url_refusal",
    "subscribe_link",
    "token_refusal",
    "topic_refusal",
]
