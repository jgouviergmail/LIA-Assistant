"""Gmail attachments, mixed into ``GoogleGmailClient``.

The attachment unit of the Gmail client — scanning the MIME part tree for the
parts that carry a file, downloading one by its handle, and picking one by
handle or by name for the tool layer — lives here because the client is
frozen at its audited size. The forward path and the browser proxy keep
calling ``get_attachment`` on the client; the mixin is where it is defined.
"""

from __future__ import annotations

import base64
import binascii
from typing import Any, Protocol

from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.clients.email_attachments import (
    EmailAttachmentContent,
    attachment_mime,
    ensure_within_bound,
    select_attachment,
)


class _GmailAttachmentReader(Protocol):
    """The read shared with the composition mixin."""

    async def get_attachment(self, message_id: str, attachment_id: str) -> bytes: ...


class _GmailHost(_GmailAttachmentReader, Protocol):
    """What the mixin needs from its host: the request seam, the message read,
    and its own download (declared here so one method may call the other)."""

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    async def get_message(
        self,
        message_id: str,
        format: str = "full",
        fields: list[str] | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]: ...


def _invalid_attachment() -> ConnectorAPIError:
    """A bounded provider failure, never its possibly private response body."""
    return ConnectorAPIError(
        connector_type="google_gmail",
        status_code=502,
        detail="The attachment data is missing, malformed or incomplete.",
    )


def decode_gmail_part_body(body: dict[str, Any]) -> bytes:
    """Read Gmail's base64url body and verify its published decoded size."""
    encoded, size = body.get("data"), body.get("size")
    if not isinstance(encoded, str) or type(size) is not int or size < 0:
        raise _invalid_attachment()
    try:
        data = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
    except binascii.Error, ValueError:
        raise _invalid_attachment() from None
    if len(data) != size:
        raise _invalid_attachment()
    return data


async def read_gmail_attachment(
    host: _GmailAttachmentReader, message_id: str, payload: dict[str, Any], listed: dict[str, Any]
) -> bytes:
    """Read an external or inline file, without publishing its encoded body."""
    handle = listed.get("attachment_id")
    if handle:
        data = await host.get_attachment(message_id, str(handle))
    else:
        part = payload
        path = str(listed.get("part_id") or "")
        for position in path.split(".") if path else ():
            part = part["parts"][int(position)]
        data = decode_gmail_part_body(part.get("body") or {})
    size = listed.get("size")
    if type(size) is not int or size < 0 or len(data) != size:
        raise _invalid_attachment()
    return data


class GmailAttachmentsMixin:
    """``users.messages.attachments`` reads for a client exposing ``_make_request``."""

    @staticmethod
    def _extract_attachment_info(payload: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Extract attachment information from message payload.

        Recursively scans MIME parts to find all attachments.

        Args:
            payload: Gmail message payload object.

        Returns:
            List of attachment info dicts with:
            - attachment_id: Gmail attachment ID
            - filename: Original filename
            - mime_type: MIME type (e.g., application/pdf)
            - size: Attachment size in bytes
            - part_id: Part ID in the message structure
        """
        attachments: list[dict[str, Any]] = []

        pending = [(payload, "")]
        while pending:
            part, part_id = pending.pop()
            body = part.get("body") or {}
            if part.get("filename"):
                attachments.append(
                    {
                        "attachment_id": body.get("attachmentId"),
                        "filename": part["filename"],
                        "mime_type": part.get("mimeType", ""),
                        "size": body.get("size"),
                        "part_id": part_id,
                    }
                )
            children = part.get("parts") or []
            pending.extend(
                (child, f"{part_id}.{i}" if part_id else str(i))
                for i, child in reversed(list(enumerate(children)))
            )

        return attachments

    async def get_attachment(
        self: _GmailHost,
        message_id: str,
        attachment_id: str,
    ) -> bytes:
        """
        Download attachment data from Gmail.

        Args:
            message_id: Gmail message ID.
            attachment_id: Gmail attachment ID.

        Returns:
            Raw attachment bytes.
        """
        response = await self._make_request(
            "GET",
            f"/users/me/messages/{message_id}/attachments/{attachment_id}",
        )

        return decode_gmail_part_body(response)

    async def download_attachment(
        self: _GmailHost,
        message_id: str,
        *,
        attachment_id: str | None = None,
        filename: str | None = None,
        max_bytes: int | None = None,
    ) -> EmailAttachmentContent:
        """Download ONE attachment of a message, by handle or by name.

        The message's part tree is read (cached when it was) to name the
        part and its MIME type; the bytes come from ``get_attachment`` — never
        for a part the listing already says exceeds ``max_bytes``.

        Args:
            message_id: Gmail message id.
            attachment_id: Gmail attachment handle; wins when given.
            filename: The name as sent, when the handle is unknown.
            max_bytes: Refuse, before downloading, a part listed larger.

        Returns:
            The file name, the MIME type as sent and the bytes.

        Raises:
            EmailAttachmentNotFoundError: No part matches.
            EmailAttachmentAmbiguousError: The name matches several parts.
            EmailAttachmentTooLargeError: The listed size exceeds the bound.
        """
        message = await self.get_message(message_id)
        listed = GmailAttachmentsMixin._extract_attachment_info(message.get("payload") or {})
        chosen = select_attachment(listed, attachment_id=attachment_id, filename=filename)
        ensure_within_bound(chosen, max_bytes=max_bytes)
        data = await read_gmail_attachment(
            self, message_id, message.get("payload") or {}, dict(chosen)
        )
        return EmailAttachmentContent(
            filename=str(chosen.get("filename") or ""),
            mime_type=attachment_mime(chosen),
            data=data,
        )


__all__ = ["GmailAttachmentsMixin"]
