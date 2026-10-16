"""
Email normalizer: Microsoft Graph message → the provider-neutral e-mail vocabulary.

Converts Microsoft Graph API message objects to the flat dict every provider
produces (``normalizers/email_message.EmailMessage``, ADR-287): top-level
headers, a clean TEXT body, an attachment list, a provider marker. It
fabricates no Gmail ``payload`` tree — the vocabulary is the contract, not
the first provider's wire format.
"""

from datetime import datetime
from email.utils import formataddr
from typing import Any

import structlog

from src.domains.connectors.clients.normalizers.html_text import html_to_text, strip_html_to_line
from src.domains.connectors.clients.normalizers.reply_trimming import clean_reply_body
from src.infrastructure.email.recipients import parse_recipients

logger = structlog.get_logger(__name__)

_SNIPPET_MAX_LENGTH = 200

# Microsoft Graph folder names → Gmail-compatible folder names
_GRAPH_FOLDER_TO_LABEL: dict[str, str] = {
    "inbox": "INBOX",
    "sentitems": "SENT",
    "drafts": "DRAFT",
    "deleteditems": "TRASH",
    "junkemail": "SPAM",
    "archive": "ARCHIVE",
}


def _parse_datetime_to_epoch_ms(dt_str: str | None) -> str:
    """Convert ISO datetime string to epoch milliseconds (Gmail internalDate format)."""
    if not dt_str:
        return "0"
    try:
        # Microsoft Graph returns ISO 8601 with timezone suffix (e.g., "2025-01-15T10:30:00Z")
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return str(int(dt.timestamp() * 1000))
    except ValueError, AttributeError:
        return "0"


def _extract_recipients(recipients: list[dict[str, Any]] | None) -> str:
    """Extract comma-separated email addresses from Microsoft Graph recipients."""
    if not recipients:
        return ""
    addresses = []
    for recipient in recipients:
        email_addr = recipient.get("emailAddress", {})
        name = email_addr.get("name", "")
        address = email_addr.get("address", "")
        if name and name != address:
            addresses.append(formataddr((name, address)))
        else:
            addresses.append(address)
    return ", ".join(addresses)


def build_graph_recipients(addresses: str) -> list[dict[str, Any]]:
    """Graph recipients for a field of addresses — the inverse of ``_extract_recipients``.

    The field is read once for every road (``infrastructure/email/recipients``):
    a display name may hold a comma, ``;`` separates as well as ``,``, and an
    address that cannot be read refuses the field rather than being sent as is.

    Args:
        addresses: Addresses separated by ``,`` or ``;``, bare or ``Name <address>``.

    Returns:
        One ``{"emailAddress": {"address", "name"}}`` per address; none for a blank field.

    Raises:
        ValueError: An address that cannot be read or is incomplete.
    """
    return [
        {"emailAddress": {"address": address, "name": name}}
        for name, address in parse_recipients(addresses)
    ]


def _build_snippet(body_content: str, body_type: str, body_preview: Any) -> str:
    """Build the short excerpt, falling back to the preview Graph already sent.

    ``search_emails`` and the list endpoints select ``bodyPreview`` and NOT
    ``body``, so a snippet derived from the body alone was EMPTY on every
    search result — while the preview sat unused in the same payload.

    Only the snippet is served this way: ``body`` means the FULL body, and
    filling it with a truncated preview would make every downstream reader
    believe it holds the whole message.

    Args:
        body_content: Raw ``body.content`` (may be empty on list endpoints).
        body_type: Raw ``body.contentType`` ("html" or "text").
        body_preview: Raw ``bodyPreview`` field, of any shape or missing.

    Returns:
        A snippet capped at ``_SNIPPET_MAX_LENGTH``, possibly empty when the
        payload carries neither a body nor a preview.
    """
    if body_type == "html":
        snippet = strip_html_to_line(body_content, max_length=_SNIPPET_MAX_LENGTH)
    else:
        snippet = body_content[:_SNIPPET_MAX_LENGTH]

    if snippet.strip():
        return snippet

    preview = str(body_preview or "").strip()
    return strip_html_to_line(preview, max_length=_SNIPPET_MAX_LENGTH) if preview else snippet


def normalize_graph_message(msg: dict[str, Any], *, keep_quoted: bool = False) -> dict[str, Any]:
    """
    Normalize a Microsoft Graph message to the provider-neutral vocabulary.

    The body is converted to TEXT here, at the client boundary — it used to
    travel as raw HTML through the registry and be converted late, by the
    agent formatter — and no Gmail ``payload`` tree is fabricated (ADR-287).

    Args:
        msg: Microsoft Graph message dict from /me/messages endpoint.
        keep_quoted: Keep the quoted history in the body — a mailbox draft is
            the person's own text, and an edit must not lose what it quotes
            (ADR-344).

    Returns:
        Dict in the ``EmailMessage`` vocabulary with the ``_provider`` marker.
    """
    msg_id = msg.get("id", "")
    thread_id = msg.get("conversationId", msg_id)
    subject = msg.get("subject", "(no subject)")

    # Extract sender
    from_data = msg.get("from", {}).get("emailAddress", {})
    from_name = from_data.get("name", "")
    from_address = from_data.get("address", "")
    from_str = formataddr((from_name, from_address)) if from_name else from_address

    # Extract recipients
    to_str = _extract_recipients(msg.get("toRecipients"))
    cc_str = _extract_recipients(msg.get("ccRecipients"))
    bcc_str = _extract_recipients(msg.get("bccRecipients"))

    # Extract body
    body_data = msg.get("body", {})
    body_content = body_data.get("content", "")
    # Graph answers "html"/"text"; a request may spell them "HTML"/"Text".
    body_type = str(body_data.get("contentType", "html")).lower()

    snippet = _build_snippet(body_content, body_type, msg.get("bodyPreview"))
    body_text = html_to_text(body_content) if body_type == "html" else body_content
    if not keep_quoted:
        body_text = clean_reply_body(body_text, subject=msg.get("subject"))

    # Build label IDs (Gmail-compatible)
    label_ids: list[str] = []
    if not msg.get("isRead", True):
        label_ids.append("UNREAD")
    if msg.get("flag", {}).get("flagStatus") == "flagged":
        label_ids.append("STARRED")
    if msg.get("isDraft", False):
        label_ids.append("DRAFT")
    # Microsoft doesn't have a direct INBOX label equivalent;
    # parentFolderId could be used but requires folder resolution

    # Attachment info
    attachments: list[dict[str, Any]] = []
    if msg.get("hasAttachments"):
        for att in msg.get("attachments", []):
            attachments.append(
                {
                    "filename": att.get("name", ""),
                    "mimeType": att.get("contentType", "application/octet-stream"),
                    "size": att.get("size", 0),
                    "attachmentId": att.get("id", ""),
                }
            )

    return {
        "id": msg_id,
        "threadId": thread_id,
        "snippet": snippet,
        "labelIds": label_ids,
        "internalDate": _parse_datetime_to_epoch_ms(msg.get("receivedDateTime")),
        "subject": subject,
        "from": from_str,
        "reply_to": _extract_recipients(msg.get("replyTo")),
        "to": to_str,
        "cc": cc_str,
        "bcc": bcc_str,
        "date": msg.get("receivedDateTime", ""),
        "body": body_text,
        "hasAttachment": msg.get("hasAttachments", False),
        "attachments": attachments,
        "sizeEstimate": msg.get("size", 0),
        "webLink": msg.get("webLink", ""),
        "_provider": "microsoft",
    }


def normalize_graph_folder(folder: dict[str, Any]) -> dict[str, str]:
    """
    Normalize a Microsoft Graph mail folder to Gmail label format.

    Args:
        folder: Microsoft Graph mailFolder dict.

    Returns:
        Dict with id and name (label format).
    """
    folder_id = folder.get("id", "")
    display_name = folder.get("displayName", "")

    # Map well-known folder display names to Gmail-compatible names.
    # The table is keyed on the COMPACT Graph names ("sentitems") while Outlook
    # reports spaced display names ("Sent Items"), so the spaces are removed
    # before the lookup — otherwise every multi-word well-known folder escaped
    # normalisation and the LLM saw a mixed vocabulary ("INBOX" + "Sent Items").
    normalized_name = _GRAPH_FOLDER_TO_LABEL.get(
        display_name.lower().replace(" ", ""), display_name
    )

    return {
        "id": folder_id,
        "name": normalized_name,
    }
