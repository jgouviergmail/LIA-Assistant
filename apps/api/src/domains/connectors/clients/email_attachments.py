"""One attachment of a message, downloaded — the same shape on every provider.

The tool layer asks for « the attachment of this message with this handle »
or « the one called X »; Gmail, Microsoft Graph and IMAP each fetch it their
own way and answer with :class:`EmailAttachmentContent`. The selection is ONE
helper the three clients share (:func:`select_attachment`), so an ambiguous
name is refused the same way everywhere and a handle nobody listed is told
apart from a name nobody sent.

Two spellings of the listing are read on purpose: the normalisers publish
``attachmentId`` / ``mimeType`` (ADR-287), the Gmail formatter still publishes
``attachment_id`` / ``mime_type`` — the helper reads both rather than
demanding a migration of every reader of a listing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class EmailAttachmentContent:
    """The bytes of one attachment, with what the sender called them."""

    filename: str
    mime_type: str
    data: bytes


class EmailAttachmentNotFoundError(LookupError):
    """No listed attachment matches the handle or the name."""


class EmailAttachmentAmbiguousError(LookupError):
    """Several listed attachments carry the name; the caller must pick a handle."""

    def __init__(self, wanted: str, candidates: Sequence[Mapping[str, Any]]) -> None:
        super().__init__(f"{len(candidates)} attachments match {wanted!r}")
        #: The name, or the stale handle, the caller asked for.
        self.filename = wanted
        self.candidates: list[Mapping[str, Any]] = list(candidates)


class EmailAttachmentTooLargeError(ValueError):
    """The listing says the part exceeds the bound — refused before any byte moves."""

    def __init__(self, *, size: int, max_bytes: int) -> None:
        super().__init__(f"attachment of {size} bytes exceeds the bound of {max_bytes} bytes")
        self.size = size
        self.max_bytes = max_bytes


def ensure_within_bound(listed: Mapping[str, Any], *, max_bytes: int | None) -> None:
    """Refuse a listed part whose published size exceeds ``max_bytes``.

    The size a listing publishes is known BEFORE the bytes are fetched, so a
    part the caller would refuse anyway is never downloaded — a stranger's
    25 MB attachment must not cost the memory of a call that ends in a
    refusal. A listing that knows no size refuses nothing here; the caller's
    check on the bytes stays the net.

    Args:
        listed: The listed attachment (``size`` when the provider says it).
        max_bytes: The bound, or None for none.

    Raises:
        EmailAttachmentTooLargeError: The published size exceeds the bound.
    """
    if max_bytes is None:
        return
    size = listed.get("size")
    if isinstance(size, int) and size > max_bytes:
        raise EmailAttachmentTooLargeError(size=size, max_bytes=max_bytes)


def attachment_handle(listed: Mapping[str, Any]) -> str | None:
    """The provider handle of a listed attachment, whichever spelling it carries."""
    handle = listed.get("attachmentId") or listed.get("attachment_id")
    return str(handle) if handle else None


def attachment_mime(listed: Mapping[str, Any]) -> str:
    """The MIME type of a listed attachment, whichever spelling it carries."""
    return str(listed.get("mimeType") or listed.get("mime_type") or "")


def select_attachment(
    attachments: Sequence[Mapping[str, Any]],
    *,
    attachment_id: str | None = None,
    filename: str | None = None,
) -> Mapping[str, Any]:
    """Pick one listed attachment by handle, else by (case-insensitive) name.

    Args:
        attachments: The message's listed attachments.
        attachment_id: The provider handle; wins when given.
        filename: The name as sent; must match exactly one part.

    Returns:
        The listed attachment.

    Raises:
        ValueError: Neither a handle nor a name was given.
        EmailAttachmentNotFoundError: Nothing matches.
        EmailAttachmentAmbiguousError: The name matches several parts.
    """
    if attachment_id:
        for listed in attachments:
            if attachment_handle(listed) == attachment_id:
                return listed
        # A handle nobody lists is STALE, not a lie: Gmail's attachment ids
        # change between two reads of the same message (measured on a real
        # mailbox, 2026-09-17), so the one served by a listing may already be
        # gone. The name decides when given; a single part is unambiguous; any
        # other case publishes the CURRENT handles for the caller to retry.
        if not filename:
            if len(attachments) == 1:
                return attachments[0]
            if not attachments:
                raise EmailAttachmentNotFoundError(f"no attachment with handle {attachment_id!r}")
            raise EmailAttachmentAmbiguousError(attachment_id, attachments)
    if not filename:
        raise ValueError("an attachment handle or a file name is required")
    wanted = filename.casefold()
    matches = [a for a in attachments if str(a.get("filename") or "").casefold() == wanted]
    if not matches:
        raise EmailAttachmentNotFoundError(f"no attachment called {filename!r}")
    if len(matches) > 1:
        raise EmailAttachmentAmbiguousError(filename, matches)
    return matches[0]


__all__ = [
    "EmailAttachmentAmbiguousError",
    "EmailAttachmentContent",
    "EmailAttachmentNotFoundError",
    "EmailAttachmentTooLargeError",
    "attachment_handle",
    "attachment_mime",
    "ensure_within_bound",
    "select_attachment",
]
