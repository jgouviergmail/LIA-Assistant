"""
Email normalizer: Microsoft Graph message → the provider-neutral e-mail vocabulary.

Converts Microsoft Graph API message objects to the flat dict every provider
produces (``normalizers/email_message.EmailMessage``, ADR-287): top-level
headers, a clean TEXT body, an attachment list, a provider marker. It
fabricates no Gmail ``payload`` tree — the vocabulary is the contract, not
the first provider's wire format.
"""

import base64
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Final

import structlog

from src.core.field_names import FIELD_MAIL_ANSWERED, FIELD_MAIL_ANSWERED_AT
from src.domains.connectors.clients.normalizers.html_text import html_to_text, strip_html_to_line
from src.domains.connectors.clients.normalizers.reply_trimming import clean_reply_body
from src.infrastructure.email.outgoing import OutgoingAttachment
from src.infrastructure.email.recipients import name_addr, parse_recipients

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
#: The well-known names of the folders a pane never lists as the person's own: its
#: system places, plus the two a mailbox holds for its own use and Graph lists all the
#: same (measured on a real mailbox). Graph serves each under its name in every locale,
#: while their display names are in the mailbox's language.
GRAPH_SYSTEM_FOLDERS: tuple[str, ...] = (
    *_GRAPH_FOLDER_TO_LABEL,
    "outbox",
    "conversationhistory",
)

#: ``PidTagLastVerbExecuted`` (tag 0x1081, an integer) and ``PidTagLastVerbExecutionTime``
#: (tag 0x1082, a UTC time), in the proptag form Graph names a MAPI property it does not
#: expose as a field ([MS-OXPROPS]; Graph, « Outlook extended properties overview »).
_LAST_VERB: Final = "Integer 0x1081"
_LAST_VERB_AT: Final = "SystemTime 0x1082"
#: The verbs that are an answer: reply to the sender, reply to all ([MS-OXOMSG]
#: 2.2.1.14). A forward (104) is not.
_ANSWER_VERBS: Final = frozenset({"102", "103"})
#: What a read of messages adds to carry the mailbox's own « answered » mark. Graph
#: promises ONE relationship expandable per request: a read asking for this one asks
#: for no other.
GRAPH_ANSWERED_MARK_EXPAND: Final = (
    f"singleValueExtendedProperties($filter=id eq '{_LAST_VERB}' or id eq '{_LAST_VERB_AT}')"
)


def _answered_mark(msg: Mapping[str, Any]) -> dict[str, Any]:
    """What a mailbox says it did last with a message, when that was to answer it.

    Args:
        msg: A Graph message; it carries the mark only where its read expanded
            ``GRAPH_ANSWERED_MARK_EXPAND``.

    Returns:
        ``FIELD_MAIL_ANSWERED`` and the instant of the verb, or nothing: a message
        never answered, forwarded last, or read without the expansion.
    """
    properties = {
        str(entry.get("id")): entry.get("value")
        for entry in msg.get("singleValueExtendedProperties") or []
        if isinstance(entry, Mapping)
    }
    if str(properties.get(_LAST_VERB)) not in _ANSWER_VERBS:
        return {}
    return {
        FIELD_MAIL_ANSWERED: True,
        FIELD_MAIL_ANSWERED_AT: graph_epoch_millis(properties.get(_LAST_VERB_AT)),
    }


def graph_epoch_millis(dt_str: object) -> str:
    """Convert ISO datetime string to epoch milliseconds (Gmail internalDate format)."""
    if not isinstance(dt_str, str) or not dt_str:
        return "0"
    try:
        # Microsoft Graph returns ISO 8601 with timezone suffix (e.g., "2025-01-15T10:30:00Z")
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return str(int(dt.timestamp() * 1000))
    except ValueError, AttributeError:
        return "0"


def _mailbox(entry: dict[str, Any] | None) -> str:
    """One Graph ``{"emailAddress": {name, address}}`` as a readable mailbox."""
    email_addr = (entry or {}).get("emailAddress") or {}
    return name_addr(email_addr.get("name"), email_addr.get("address"))


def _extract_recipients(recipients: list[dict[str, Any]] | None) -> str:
    """Comma-separated readable mailboxes of Microsoft Graph recipients."""
    return ", ".join(mailbox for mailbox in map(_mailbox, recipients or []) if mailbox)


def graph_file_attachment(attachment: OutgoingAttachment) -> dict[str, str]:
    """One file as Graph carries it inside a message (ADR-321).

    Args:
        attachment: The file.

    Returns:
        The ``fileAttachment`` resource, its bytes in base64.
    """
    content_type = attachment.mime_type
    if attachment.charset:
        content_type = f"{content_type}; charset={attachment.charset}"
    return {
        "@odata.type": "#microsoft.graph.fileAttachment",
        "name": attachment.filename,
        "contentType": content_type,
        "contentBytes": base64.b64encode(attachment.data).decode("ascii"),
    }


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

    from_str = _mailbox(msg.get("from"))

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
        "internalDate": graph_epoch_millis(msg.get("receivedDateTime")),
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
        # What its mailbox says of it, where the read asked (ADR-379).
        **_answered_mark(msg),
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
