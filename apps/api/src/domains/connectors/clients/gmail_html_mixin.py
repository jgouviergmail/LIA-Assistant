"""The HTML of a Gmail message, mixed into ``GoogleGmailClient`` (ADR-369, D3).

Which parts are the body's HTML is ``mail_html``'s rule. The ``format=full``
payload is walked in document order; Gmail serves a part's bytes decoded from
their transfer encoding but still in the part's own charset, which its
``Content-Type`` names. A part too large to travel inline carries an
attachment handle and is read through it. The message is the cached one when
the cache holds it: a sent message's HTML never changes. The images it carries and
the way out it names are read from the same payload (``mail_inline_images``,
``mail_unsubscribe``).
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
from src.domains.connectors.clients.mail_inline_images import InlineBudget, content_id_of
from src.domains.connectors.clients.mail_unsubscribe import Unsubscribe, read_unsubscribe


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


def part_header(part: dict[str, Any], name: str) -> str | None:
    """The value of a part's header, whatever its case."""
    for header in part.get("headers") or []:
        if str(header.get("name") or "").lower() == name:
            return str(header.get("value") or "")
    return None


def identified_parts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """The parts carrying a ``Content-ID``, those of a forwarded message left out."""
    found: list[dict[str, Any]] = []
    pending = [payload]
    while pending:
        part = pending.pop()
        if str(part.get("mimeType") or "").lower() == ATTACHED_MESSAGE_TYPE:
            continue
        if part_header(part, "content-id"):
            found.append(part)
        pending.extend(reversed(part.get("parts") or []))
    return found


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

    async def read_inline_images(
        self: _GmailHtmlHost, message_id: str, cids: set[str], budget: InlineBudget
    ) -> None:
        """Read into ``budget`` the images of a message its HTML names."""
        message = await self.get_message(message_id)
        for part in identified_parts(message.get("payload") or {}):
            cid = content_id_of(part_header(part, "content-id"))
            body = part.get("body") or {}
            if cid not in cids or not budget.worth_reading(body.get("size")):
                continue
            handle = body.get("attachmentId")
            data = (
                await self.get_attachment(message_id, str(handle))
                if handle
                else decode_gmail_part_body(body)
            )
            budget.admit(str(cid), str(part.get("mimeType") or ""), data)

    async def read_unsubscribe(self: _GmailHtmlHost, message_id: str) -> Unsubscribe | None:
        """The ways out a message names."""
        payload = (await self.get_message(message_id)).get("payload") or {}
        return read_unsubscribe(
            part_header(payload, "list-unsubscribe"),
            part_header(payload, "list-unsubscribe-post"),
        )
