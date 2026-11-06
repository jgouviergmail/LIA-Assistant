"""How a provider's message becomes what the mail screen draws (ADR-369): pure.

The three normalisers speak one vocabulary (``EmailMessage``, ADR-287): header
strings, Gmail-style labels, epoch milliseconds. The screen wants mailboxes
read apart (a quoted name may hold a comma), an instant, two flags — and the
attachments, which Gmail lists in its MIME parts and the two others in the
message's own list, each with its handle AND its name (a Gmail handle expires
between two reads, ADR-296).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from email.utils import getaddresses
from typing import Any

from src.domains.connectors.clients.email_attachments import declares_attachments
from src.domains.connectors.clients.gmail_attachments_mixin import GmailAttachmentsMixin
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.models import ConnectorType
from src.domains.workbench.previews import can_be_shown
from src.domains.workbench.schemas.mail import MailAddress, MailAttachment


def addresses(header: object) -> list[MailAddress]:
    """A header's mailboxes, read apart; an empty or unreadable header names none."""
    if not isinstance(header, str) or not header.strip():
        return []
    return [
        MailAddress(name=name, address=address)
        for name, address in getaddresses([header])
        if name or address
    ]


def first_address(header: object) -> MailAddress | None:
    """A header's first mailbox (a sender), or None."""
    found = addresses(header)
    return found[0] if found else None


def received_at(value: object) -> datetime | None:
    """Epoch milliseconds, as the normalisers carry them; absent, 0 or absurd is no date."""
    try:
        millis = int(str(value))
        return datetime.fromtimestamp(millis / 1000, UTC) if millis > 0 else None
    except ValueError, OverflowError, OSError:
        return None


def is_read(message: Mapping[str, Any]) -> bool:
    """Read unless Gmail-style labels say ``UNREAD``."""
    return "UNREAD" not in (message.get("labelIds") or [])


def is_starred(message: Mapping[str, Any]) -> bool:
    """Starred (flagged) when Gmail-style labels say ``STARRED``."""
    return "STARRED" in (message.get("labelIds") or [])


def has_attachments(message: Mapping[str, Any]) -> bool:
    """Whether a row carries files: the normaliser's word, else Gmail's top-level type."""
    if message.get("hasAttachment"):
        return True
    headers = (message.get("payload") or {}).get("headers") or []
    return any(
        declares_attachments(header.get("value"))
        for header in headers
        if str(header.get("name")).lower() == "content-type"
    )


def user_labels(message: Mapping[str, Any], provider: ConnectorType) -> list[str]:
    """The person's own Gmail labels on a message; a system one is a flag or a place,
    never a label of theirs. Elsewhere the Gmail-style list carries flags alone."""
    if provider is not ConnectorType.GOOGLE_GMAIL:
        return []
    return [
        str(label)
        for label in message.get("labelIds") or []
        if str(label).upper() not in GoogleGmailClient.GMAIL_SYSTEM_LABELS
    ]


def attachments_of(raw: Mapping[str, Any], provider: ConnectorType) -> list[MailAttachment]:
    """Gmail's from its MIME parts; Graph's and IMAP's from the message's own list.

    A Gmail part goes by its place in the message: its attachment id changes at each read.
    """
    if provider is ConnectorType.GOOGLE_GMAIL:
        parts = GmailAttachmentsMixin._extract_attachment_info(raw.get("payload") or {})
        return [
            _attachment(
                part.get("part_id") or part.get("attachment_id"),
                part.get("filename"),
                part.get("mime_type"),
                part,
            )
            for part in parts
        ]
    return [
        _attachment(item.get("attachmentId"), item.get("filename"), item.get("mimeType"), item)
        for item in raw.get("attachments") or []
    ]


def _attachment(
    handle: object, filename: object, mime_type: object, listed: Mapping[str, Any]
) -> MailAttachment:
    name = str(filename or "")
    kind = str(mime_type or "")
    return MailAttachment(
        id=str(handle) if handle else None,
        filename=name,
        mime_type=kind,
        size=listed.get("size"),
        previewable=can_be_shown(kind, name),
    )
