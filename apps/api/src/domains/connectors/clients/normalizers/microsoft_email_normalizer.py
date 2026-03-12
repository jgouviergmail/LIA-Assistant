"""
Email normalizer: Microsoft Graph message → dict format Gmail API.

Converts Microsoft Graph API message objects to the dict structure
expected by emails_tools.py (same format as GoogleGmailClient).
"""

import re
from datetime import datetime
from html import unescape
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# HTML tag stripping for snippet generation
_HTML_TAG_RE = re.compile(r"<[^>]+>")

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

# Gmail-style query operators → Microsoft Graph KQL/OData patterns
# Supports both unquoted values (from:john) and quoted multi-word values (subject:"meeting notes")
_GMAIL_OPERATOR_PATTERN = re.compile(
    r'(from|to|subject|after|before|label|is|has|in):("(?:[^"\\]|\\.)*"|\S+)'
)
_GMAIL_NEGATION_PATTERN = re.compile(
    r'-(?:in|label|is|has|from|to|subject|after|before):("(?:[^"\\]|\\.)*"|\S+)'
)

# Well-known Microsoft folder display names → folder IDs
_WELL_KNOWN_FOLDERS: dict[str, str] = {
    "inbox": "inbox",
    "sent": "sentitems",
    "sentitems": "sentitems",
    "sent messages": "sentitems",
    "drafts": "drafts",
    "draft": "drafts",
    "trash": "deleteditems",
    "deleted items": "deleteditems",
    "deleteditems": "deleteditems",
    "junk": "junkemail",
    "spam": "junkemail",
    "junkemail": "junkemail",
    "archive": "archive",
}


def _normalize_date_to_iso8601(date_str: str) -> str:
    """Convert various date formats to ISO 8601 for Microsoft Graph OData filters.

    Gmail-style queries use formats like ``2025/12/10``, ``2025-12-10``, or
    ``2025/1/5``.  Microsoft Graph OData requires ISO 8601 datetime strings
    (``2025-12-10T00:00:00Z``).
    """
    # Strip quotes
    date_str = date_str.strip("'\"")

    # Try common formats
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%dT00:00:00Z")
        except ValueError:
            continue

    # Fallback: return as-is with T00:00:00Z suffix if it looks like a date
    clean = date_str.replace("/", "-")
    if re.match(r"\d{4}-\d{1,2}-\d{1,2}$", clean):
        return f"{clean}T00:00:00Z"

    return date_str


def _strip_html(html: str) -> str:
    """Strip HTML tags and decode entities for plain text snippet."""
    text = _HTML_TAG_RE.sub("", html)
    text = unescape(text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_datetime_to_epoch_ms(dt_str: str | None) -> str:
    """Convert ISO datetime string to epoch milliseconds (Gmail internalDate format)."""
    if not dt_str:
        return "0"
    try:
        # Microsoft Graph returns ISO 8601 with timezone suffix (e.g., "2025-01-15T10:30:00Z")
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return str(int(dt.timestamp() * 1000))
    except (ValueError, AttributeError):
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
            addresses.append(f"{name} <{address}>")
        else:
            addresses.append(address)
    return ", ".join(addresses)


def normalize_graph_message(msg: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize a Microsoft Graph message to Gmail API dict format.

    Converts the Microsoft Graph message structure to match what
    emails_tools.py expects (same format as GoogleGmailClient).

    Args:
        msg: Microsoft Graph message dict from /me/messages endpoint.

    Returns:
        Dict in Gmail API message format with _provider marker.
    """
    msg_id = msg.get("id", "")
    thread_id = msg.get("conversationId", msg_id)
    subject = msg.get("subject", "(no subject)")

    # Extract sender
    from_data = msg.get("from", {}).get("emailAddress", {})
    from_name = from_data.get("name", "")
    from_address = from_data.get("address", "")
    from_str = f"{from_name} <{from_address}>" if from_name else from_address

    # Extract recipients
    to_str = _extract_recipients(msg.get("toRecipients"))
    cc_str = _extract_recipients(msg.get("ccRecipients"))
    bcc_str = _extract_recipients(msg.get("bccRecipients"))

    # Extract body
    body_data = msg.get("body", {})
    body_content = body_data.get("content", "")
    body_type = body_data.get("contentType", "html")

    # Generate snippet from body
    if body_type == "html":
        snippet = _strip_html(body_content)[:_SNIPPET_MAX_LENGTH]
    else:
        snippet = body_content[:_SNIPPET_MAX_LENGTH]

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

    # Build Gmail-compatible headers
    headers = [
        {"name": "From", "value": from_str},
        {"name": "To", "value": to_str},
        {"name": "Subject", "value": subject},
        {"name": "Date", "value": msg.get("receivedDateTime", "")},
    ]
    if cc_str:
        headers.append({"name": "Cc", "value": cc_str})
    if bcc_str:
        headers.append({"name": "Bcc", "value": bcc_str})

    return {
        "id": msg_id,
        "threadId": thread_id,
        "snippet": snippet,
        "labelIds": label_ids,
        "internalDate": _parse_datetime_to_epoch_ms(msg.get("receivedDateTime")),
        "payload": {
            "headers": headers,
            "mimeType": "text/html" if body_type == "html" else "text/plain",
        },
        "subject": subject,
        "from": from_str,
        "to": to_str,
        "date": msg.get("receivedDateTime", ""),
        "body": body_content,
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

    # Map well-known folder display names to Gmail-compatible names
    normalized_name = _GRAPH_FOLDER_TO_LABEL.get(display_name.lower(), display_name)

    return {
        "id": folder_id,
        "name": normalized_name,
    }


def build_search_filter(gmail_query: str) -> dict[str, str | None]:
    """
    Translate a Gmail-style query to Microsoft Graph $search, $filter, and folder parameters.

    Microsoft Graph uses KQL (Keyword Query Language) for $search
    and OData for $filter. Folder-based filtering uses endpoint routing
    (``/me/mailFolders/{id}/messages``) because ``parentFolderId`` is not
    a supported ``$filter`` property.

    Important Graph API constraints:
    - ``$search`` and ``$orderby`` are mutually exclusive.
    - ``$search`` and ``$filter`` cannot be combined.

    Args:
        gmail_query: Gmail-style query (e.g., "from:john subject:meeting label:INBOX").

    Returns:
        Dict with optional keys:
        - ``search``: KQL search string (quoted).
        - ``filter``: OData filter expression.
        - ``folder``: Well-known folder ID for endpoint routing (e.g., "inbox").
    """
    # Strip negation operators (Microsoft $search doesn't support NOT well)
    clean_query = _GMAIL_NEGATION_PATTERN.sub("", gmail_query).strip()

    search_parts: list[str] = []
    filter_parts: list[str] = []
    remaining_text: list[str] = []
    folder: str | None = None

    # Track position for extracting non-operator text
    last_end = 0

    for match in _GMAIL_OPERATOR_PATTERN.finditer(clean_query):
        # Capture text before this operator
        before = clean_query[last_end : match.start()].strip()
        if before:
            remaining_text.append(before)
        last_end = match.end()

        operator = match.group(1).lower()
        value = match.group(2).strip('"')

        if operator == "from":
            search_parts.append(f"from:{value}")
        elif operator == "to":
            search_parts.append(f"to:{value}")
        elif operator == "subject":
            search_parts.append(f"subject:{value}")
        elif operator == "after":
            iso_date = _normalize_date_to_iso8601(value)
            filter_parts.append(f"receivedDateTime ge {iso_date}")
        elif operator == "before":
            iso_date = _normalize_date_to_iso8601(value)
            filter_parts.append(f"receivedDateTime le {iso_date}")
        elif operator == "has" and value == "attachment":
            filter_parts.append("hasAttachments eq true")
        elif operator == "is" and value == "unread":
            filter_parts.append("isRead eq false")
        elif operator == "is" and value == "read":
            filter_parts.append("isRead eq true")
        elif operator in ("label", "in"):
            # Folder-based filtering via endpoint routing, not $filter
            folder_id = _WELL_KNOWN_FOLDERS.get(value.lower())
            if folder_id:
                folder = folder_id

    # Capture remaining text after last operator
    after_last = clean_query[last_end:].strip()
    if after_last:
        remaining_text.append(after_last)

    # Combine search parts with any remaining free text
    if remaining_text:
        search_parts.extend(remaining_text)

    search_str = " ".join(search_parts) if search_parts else None
    filter_str = " and ".join(filter_parts) if filter_parts else None

    # Default to inbox when no folder explicitly requested.
    # Microsoft Graph /me/messages searches ALL folders (including Junk, Deleted Items,
    # Sent Items). This aligns with Gmail (excludes sent/draft/trash/spam by default)
    # and Apple IMAP (defaults to INBOX).
    if folder is None:
        folder = "inbox"

    return {
        "search": f'"{search_str}"' if search_str else None,
        "filter": filter_str,
        "folder": folder,
    }
