"""The HTML of a Gmail message, mixed into ``GoogleGmailClient`` (ADR-369, D3).

Which parts are the body's HTML is ``mail_html``'s rule. The ``format=full``
payload is walked in document order; Gmail serves a part's bytes decoded from
their transfer encoding but still in the part's own charset, which its
``Content-Type`` names. A part too large to travel inline carries an
attachment handle and is read through it. The message is the cached one when
the cache holds it: a sent message's HTML never changes.
"""

from __future__ import annotations

from email.message import Message
from typing import Any, Protocol

from src.domains.connectors.clients.gmail_attachments_mixin import decode_gmail_part_body
from src.domains.connectors.clients.mail_html import (
    ATTACHED_MESSAGE_TYPE,
    HTML_TYPE,
    decode_text,
)


class _GmailHtmlHost(Protocol):
    """What the mixin needs from its host: the message read and the part download."""

    async def get_message(
        self,
        message_id: str,
        format: str = "full",
        fields: list[str] | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]: ...

    async def get_attachment(self, message_id: str, attachment_id: str) -> bytes: ...


def html_body_parts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """The body's ``text/html`` parts, in document order (``mail_html``)."""
    found: list[dict[str, Any]] = []
    pending = [payload]
    while pending:
        part = pending.pop()
        mime = str(part.get("mimeType") or "").lower()
        if part.get("filename") or mime == ATTACHED_MESSAGE_TYPE:
            continue
        if mime == HTML_TYPE:
            found.append(part)
        pending.extend(reversed(part.get("parts") or []))
    return found


def part_charset(part: dict[str, Any]) -> str | None:
    """The charset a part's ``Content-Type`` names, if it names one."""
    for header in part.get("headers") or []:
        if str(header.get("name") or "").lower() == "content-type":
            holder = Message()
            holder["Content-Type"] = str(header.get("value") or "")
            return holder.get_content_charset()
    return None


class GmailHtmlMixin:
    """The HTML body of Gmail messages."""

    async def get_message_html(self: _GmailHtmlHost, message_id: str) -> str | None:
        """The message's HTML body, or None when it carries none."""
        message = await self.get_message(message_id)
        pieces: list[str] = []
        for part in html_body_parts(message.get("payload") or {}):
            body = part.get("body") or {}
            handle = body.get("attachmentId")
            if handle:
                data = await self.get_attachment(message_id, str(handle))
            elif body.get("data"):
                data = decode_gmail_part_body(body)
            else:
                continue
            pieces.append(decode_text(data, part_charset(part)))
        return "".join(pieces) or None
