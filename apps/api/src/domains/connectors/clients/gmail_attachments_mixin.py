"""Gmail attachments, mixed into ``GoogleGmailClient``.

The attachment unit of the Gmail client — scanning the MIME part tree for the
parts that carry a file, downloading one by its handle, and picking one by
handle or by name for the tool layer — lives here because the client is
frozen at its audited size. The forward path and the browser proxy keep
calling ``get_attachment`` on the client; the mixin is where it is defined.
"""

from __future__ import annotations

import base64
from typing import Any, Protocol

from src.domains.connectors.clients.email_attachments import (
    EmailAttachmentContent,
    attachment_mime,
    ensure_within_bound,
    select_attachment,
)


class _GmailHost(Protocol):
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

    async def get_attachment(self, message_id: str, attachment_id: str) -> bytes: ...


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

        def scan_parts(parts: list[dict[str, Any]], parent_part_id: str = "") -> None:
            for i, part in enumerate(parts):
                part_id = f"{parent_part_id}.{i}" if parent_part_id else str(i)
                mime_type = part.get("mimeType", "")
                filename = part.get("filename", "")
                body = part.get("body", {})

                # Check if this is an attachment (has filename and attachmentId)
                if filename and body.get("attachmentId"):
                    attachments.append(
                        {
                            "attachment_id": body["attachmentId"],
                            "filename": filename,
                            "mime_type": mime_type,
                            "size": body.get("size", 0),
                            "part_id": part_id,
                        }
                    )

                # Recurse into nested parts
                if "parts" in part:
                    scan_parts(part["parts"], part_id)

        # Start scanning from top-level parts
        if "parts" in payload:
            scan_parts(payload["parts"])

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

        # Gmail returns base64url-encoded data
        data_b64 = response.get("data", "")
        # Convert base64url to standard base64
        data_b64 = data_b64.replace("-", "+").replace("_", "/")
        # Add padding if needed
        padding = len(data_b64) % 4
        if padding:
            data_b64 += "=" * (4 - padding)

        return base64.b64decode(data_b64)

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
        data = await self.get_attachment(message_id, str(chosen["attachment_id"]))
        return EmailAttachmentContent(
            filename=str(chosen.get("filename") or ""),
            mime_type=attachment_mime(chosen),
            data=data,
        )


__all__ = ["GmailAttachmentsMixin"]
