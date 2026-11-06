"""How a message says it can be left: one rule for every mail provider (ADR-369, lot 3).

``List-Unsubscribe`` (RFC 2369) is a sender's words, so nothing in it is taken on
trust: only an https page and a mail address are kept, the first of each. One-click
(RFC 8058) is the sender's own promise in ``List-Unsubscribe-Post``, and it needs a
page to post to. A header past any honest length reads as none. Display and act
are the caller's: this module only reads.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlsplit

#: What RFC 8058 has a sender write, and what the POST carries.
ONE_CLICK_BODY: Final = "List-Unsubscribe=One-Click"
#: Longer than any real header: a stranger's text is bounded before it is read.
_HEADER_MAX_CHARS: Final = 2048
_TARGET: Final = re.compile(r"<([^<>]*)>")
_FOLD: Final = re.compile(r"\r?\n[ \t]*")
_MAIL_SCHEME: Final = "mailto:"


@dataclass(frozen=True)
class Unsubscribe:
    """The ways out a message names."""

    web_url: str | None
    mail_to: str | None
    one_click: bool


def _web_page(target: str) -> str | None:
    """``target`` when it is an https page naming a host and no credentials."""
    try:
        parts = urlsplit(target)
        credentials = parts.username or parts.password
    except ValueError:
        return None
    return target if parts.scheme == "https" and parts.hostname and not credentials else None


def _mail_address(target: str) -> str | None:
    """What follows ``mailto:`` when it names a mailbox."""
    if not target.lower().startswith(_MAIL_SCHEME):
        return None
    address = target[len(_MAIL_SCHEME) :]
    return address if address.split("?", 1)[0].strip() else None


def read_unsubscribe(header: str | None, post_header: str | None) -> Unsubscribe | None:
    """The ways out of a message.

    Args:
        header: Its ``List-Unsubscribe``, as received.
        post_header: Its ``List-Unsubscribe-Post``, as received.

    Returns:
        What may be followed; None when nothing may.
    """
    if not header or len(header) > _HEADER_MAX_CHARS:
        return None
    targets = [target.strip() for target in _TARGET.findall(_FOLD.sub("", header))]
    web_url = next(filter(None, map(_web_page, targets)), None)
    mail_to = next(filter(None, map(_mail_address, targets)), None)
    if web_url is None and mail_to is None:
        return None
    promised = (post_header or "").strip().lower() == ONE_CLICK_BODY.lower()
    return Unsubscribe(web_url=web_url, mail_to=mail_to, one_click=promised and web_url is not None)
