"""
The body and the attachments of an e-mail message, for the finishing step of a read.

``GmailFormatter`` reads a message — Gmail's MIME tree, or the Apple/Microsoft
messages normalised to look like it (ADR-287) — for the body text and the
attachment list that ``agents/emails/message_finishing.py`` hands on. It is a
namespace of static methods, never instantiated.

What this module used to hold went with ADR-194 and its 2026-10-22 amendment:
``BaseFormatter``, ``format_item``, ``FIELD_EXTRACTORS`` and
``OPERATION_DEFAULT_FIELDS`` first, their last consumer gone, then every
extractor and date formatter only they reached — ``ContactsFormatter`` whole,
whose remaining callers were never called themselves. What stays here is
reached from a registered tool.

Usage Example:
    from src.domains.agents.tools.formatters import GmailFormatter

    body = GmailFormatter._extract_body(message)
    attachments = GmailFormatter._extract_attachments(message)
"""

from typing import Any

from src.core.i18n import resolve_language
from src.core.i18n_api_messages import APIMessages

# =============================================================================
# GMAIL FORMATTER
# =============================================================================


class GmailFormatter:
    """
    Body and attachment extraction for an e-mail message.

    Provider-aware: Apple and Microsoft hand over a top-level text body, Gmail a
    MIME tree (ADR-287).
    """

    # =========================================================================
    # FIELD EXTRACTION HELPERS
    # =========================================================================

    @staticmethod
    def _extract_body(message: dict[str, Any]) -> str:
        """Extract email body content (provider-aware).

        - Apple and Microsoft: body is at top-level, already text (ADR-287)
        - Gmail: body is in payload.parts (base64url encoded, needs recursive extraction)
        """
        # Fast path: top-level body (Apple/Microsoft normalizer, or already enriched)
        top_level_body = message.get("body")
        if isinstance(top_level_body, str) and top_level_body:
            # Every provider hands TEXT at its client boundary (ADR-287): the
            # Graph HTML used to be converted here, late, after the raw markup
            # had travelled through the registry.
            return top_level_body

        # Gmail path: extract from payload parts
        payload = message.get("payload", {})
        if not payload:
            return ""

        # Import here to avoid circular dependency
        from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient

        return GoogleGmailClient._extract_body_recursive(payload)

    @staticmethod
    def _extract_attachments(
        message: dict[str, Any], locale: str | None = None
    ) -> list[dict[str, str]]:
        """
        Extract attachments from email message.

        Returns list of attachments with filename and Gmail URL.

        Args:
            message: Gmail message object
            locale: User's locale for i18n placeholders

        Returns:
            List of dicts with keys:
            - filename: Attachment filename
            - gmail_url: URL to view/download attachment in Gmail
            - mime_type: MIME type of attachment
            - size: Size in bytes (if available)

        Example:
            >>> attachments = _extract_attachments(message)
            >>> print(attachments)
            [
                {
                    "filename": "document.pdf",
                    "gmail_url": "https://mail.google.com/mail/u/0/#all/18f3c...",
                    "mime_type": "application/pdf",
                    "size": 245678
                }
            ]

        Note:
            Gmail API requires format=full to get attachment metadata.
            Attachment bodies are NOT extracted (use attachmentId if needed).
        """
        # Get language from locale
        lang = resolve_language(locale)

        attachments = []
        payload = message.get("payload", {})
        message_id = message.get("id", "")

        def _extract_from_parts(parts: list[dict[str, Any]]) -> None:
            """Recursively extract attachments from message parts."""
            for part in parts:
                # Check if this part is an attachment
                filename = part.get("filename", "")
                mime_type = part.get("mimeType", "")
                body = part.get("body", {})
                attachment_id = body.get("attachmentId")

                # Gmail marks attachments with either:
                # 1. Non-empty filename
                # 2. Content-Disposition: attachment header
                # Accept attachment if Gmail provides an attachmentId, even if filename is empty
                if attachment_id:
                    # Build Gmail URL (same as message URL, Gmail handles attachment display)
                    gmail_url = (
                        f"https://mail.google.com/mail/u/0/#all/{message_id}" if message_id else ""
                    )

                    if not filename:
                        filename = APIMessages.attachment_placeholder(lang)

                    attachments.append(
                        {
                            "filename": filename,
                            "gmail_url": gmail_url,
                            "mime_type": mime_type,
                            "size": body.get("size", 0),
                            "attachment_id": attachment_id,
                            "message_id": message_id,
                        }
                    )

                # Recurse into nested parts (multipart messages)
                if "parts" in part:
                    _extract_from_parts(part["parts"])

        # Start extraction from payload
        if "parts" in payload:
            _extract_from_parts(payload["parts"])

        return attachments


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "GmailFormatter",
]
