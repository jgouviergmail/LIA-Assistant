"""
Email normalizer: IMAP MailMessage → dict format Gmail API.

Converts imap_tools MailMessage objects to the dict structure
expected by emails_tools.py (same format as GoogleGmailClient).
"""

import re
from datetime import UTC, date, datetime
from html import unescape
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Gmail query operators → imap_tools AND criteria
_GMAIL_OPERATOR_PATTERN = re.compile(r"(from|to|subject|after|before|label|is|has|in):(\S+)")
# Gmail negation operators (e.g., -in:sent, -label:promo) — IMAP has no equivalent,
# these are stripped from the query to avoid polluting full-text search
_GMAIL_NEGATION_PATTERN = re.compile(r"-(?:in|label|is|has|from|to|subject|after|before):(\S+)")

# HTML tag stripping for snippet generation
_HTML_TAG_RE = re.compile(r"<[^>]+>")

_SNIPPET_MAX_LENGTH = 200

# Gmail folder names → IMAP folder names (iCloud convention)
_GMAIL_FOLDER_TO_IMAP: dict[str, str] = {
    "sent": "Sent Messages",
    "trash": "Trash",
    "drafts": "Drafts",
    "draft": "Drafts",
    "spam": "Junk",
    "junk": "Junk",
    "inbox": "INBOX",
    "archive": "Archive",
}


def normalize_imap_message(msg: Any, folder: str) -> dict[str, Any]:
    """
    Normalize an imap_tools MailMessage to Gmail API dict format.

    IMPORTANT: This must be called WITHIN the MailBox context manager,
    as MailMessage properties are cached_property that access the connection.

    Args:
        msg: imap_tools MailMessage object.
        folder: IMAP folder name the message was fetched from.

    Returns:
        Dict matching Gmail API message format.
    """
    uid = str(msg.uid)

    # =========================================================================
    # Body: extract text, prefer plain text over HTML-stripped
    # Store at TOP-LEVEL to bypass GmailFormatter._extract_body_recursive()
    # which expects base64url-encoded data (Gmail API format)
    # =========================================================================
    body_text = msg.text or ""
    if not body_text and msg.html:
        body_text = _strip_html(msg.html)
    snippet = body_text[:_SNIPPET_MAX_LENGTH].strip()

    # =========================================================================
    # Headers: both as nested list (Gmail API compat) and top-level (card compat)
    # =========================================================================
    headers = []
    subject = msg.subject or ""
    from_value = msg.from_ or ""
    to_value = ""
    cc_value = ""

    if from_value:
        headers.append({"name": "From", "value": from_value})
    if msg.to:
        to_value = ", ".join(msg.to) if isinstance(msg.to, list | tuple) else str(msg.to)
        headers.append({"name": "To", "value": to_value})
    if subject:
        headers.append({"name": "Subject", "value": subject})
    if msg.date_str:
        headers.append({"name": "Date", "value": msg.date_str})
    if msg.cc:
        cc_value = ", ".join(msg.cc) if isinstance(msg.cc, list | tuple) else str(msg.cc)
        headers.append({"name": "Cc", "value": cc_value})

    # =========================================================================
    # Attachments: top-level for direct access by _enrich_email()
    # =========================================================================
    attachments = []
    for att in msg.attachments:
        attachments.append(
            {
                "filename": att.filename,
                "mimeType": att.content_type,
                "size": len(att.payload) if att.payload else 0,
            }
        )

    # =========================================================================
    # Labels: IMAP flags → Gmail-compatible labelIds
    # imap_tools MailMessage.flags returns tuple of str like ('\\Seen', '\\Flagged')
    # =========================================================================
    label_ids = [folder]
    try:
        flags = msg.flags  # cached_property — must be accessed within MailBox context
    except Exception:
        flags = ()
    # \\Seen absent = unread (IMAP convention: absence of flag = not seen)
    if "\\Seen" not in flags:
        label_ids.append("UNREAD")
    if "\\Flagged" in flags:
        label_ids.append("STARRED")

    # =========================================================================
    # Internal date as epoch milliseconds
    # =========================================================================
    internal_date: str | None = None
    if msg.date:
        if isinstance(msg.date, datetime):
            internal_date = str(int(msg.date.timestamp() * 1000))
        elif isinstance(msg.date, date):
            internal_date = str(
                int(datetime.combine(msg.date, datetime.min.time(), tzinfo=UTC).timestamp() * 1000)
            )

    return {
        "id": uid,
        "threadId": uid,  # IMAP has no thread concept
        "labelIds": label_ids,
        "snippet": snippet,
        # Top-level fields for EmailCard (bypass Gmail-specific extraction)
        "subject": subject,
        "from": from_value,
        "to": to_value,
        "cc": cc_value,
        "body": body_text,
        "unread": "UNREAD" in label_ids,
        "hasAttachment": len(attachments) > 0,
        # Nested payload for Gmail API compatibility
        "payload": {
            "headers": headers,
            "parts": [],  # Not needed — body is at top-level
            "filename": attachments[0]["filename"] if attachments else "",
        },
        "attachments": attachments,
        "internalDate": internal_date,
        # Provider marker for downstream formatters and display components.
        # Used to determine web URL availability and "read more" link text.
        "_provider": "apple",
    }


def normalize_imap_folder(folder_name: str) -> dict[str, Any]:
    """
    Normalize an IMAP folder to Gmail label format.

    Args:
        folder_name: IMAP folder name.

    Returns:
        Dict matching Gmail label format.
    """
    # Map common IMAP folders to Gmail system labels
    system_folders = {
        "INBOX": "system",
        "Sent": "system",
        "Sent Messages": "system",
        "Drafts": "system",
        "Trash": "system",
        "Junk": "system",
        "Spam": "system",
        "Archive": "system",
    }
    folder_type = system_folders.get(folder_name, "user")

    return {
        "id": folder_name,
        "name": folder_name,
        "type": folder_type,
    }


def convert_imap_query(gmail_query: str) -> tuple[Any, str | None]:
    """
    Convert a Gmail-style query string to imap_tools AND criteria.

    Args:
        gmail_query: Gmail query string (e.g., "from:user@example.com is:unread").

    Returns:
        Tuple of (imap_tools AND criteria, target_folder or None).
        target_folder is set when "label:X" is found in the query.
    """
    from imap_tools import AND

    criteria: dict[str, Any] = {}
    target_folder: str | None = None

    # Step 1: Strip negation operators (IMAP searches one folder at a time,
    # folder exclusions like -in:sent have no IMAP equivalent)
    cleaned_query = _GMAIL_NEGATION_PATTERN.sub("", gmail_query).strip()
    if cleaned_query != gmail_query:
        logger.debug(
            "imap_query_negations_stripped",
            original=gmail_query,
            cleaned=cleaned_query,
        )

    # Step 2: Extract known positive operators
    query_without_operators = cleaned_query
    for match in _GMAIL_OPERATOR_PATTERN.finditer(cleaned_query):
        operator = match.group(1).lower()
        value = match.group(2)
        query_without_operators = query_without_operators.replace(match.group(0), "").strip()

        if operator == "from":
            criteria["from_"] = value
        elif operator == "to":
            criteria["to"] = value
        elif operator == "subject":
            criteria["subject"] = value
        elif operator == "after":
            criteria["date_gte"] = _parse_date(value)
        elif operator == "before":
            criteria["date_lt"] = _parse_date(value)
        elif operator == "label":
            target_folder = _GMAIL_FOLDER_TO_IMAP.get(value, value)
        elif operator == "is":
            if value == "unread":
                criteria["seen"] = False
            elif value == "read":
                criteria["seen"] = True
            elif value == "starred":
                criteria["flagged"] = True
            elif value in ("important", "snoozed"):
                logger.debug("imap_query_unsupported_operator", operator=f"is:{value}")
        elif operator == "has":
            if value == "attachment":
                logger.debug("imap_query_unsupported_operator", operator="has:attachment")
        elif operator == "in":
            if value == "anywhere":
                logger.debug("imap_query_unsupported_operator", operator="in:anywhere")
            else:
                # in:sent, in:trash, in:drafts → select IMAP folder
                target_folder = _GMAIL_FOLDER_TO_IMAP.get(value, value)

    # Remaining text becomes full-text search
    remaining = query_without_operators.strip()
    if remaining:
        criteria["text"] = remaining

    # Build AND criteria (filter None values from date parsing)
    filtered_criteria = {k: v for k, v in criteria.items() if v is not None}

    if filtered_criteria:
        return AND(**filtered_criteria), target_folder
    return AND(all=True), target_folder


def _parse_date(date_str: str) -> date | None:
    """Parse date from Gmail query format (YYYY/MM/DD or YYYY-MM-DD)."""
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    logger.warning("imap_query_invalid_date", date_str=date_str)
    return None


def _strip_html(html: str) -> str:
    """Strip HTML tags and decode entities for snippet generation."""
    text = _HTML_TAG_RE.sub(" ", html)
    text = unescape(text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()
