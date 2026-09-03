"""Rendering a Gmail thread as the Markdown document a space indexes (ADR-262).

Pure: no session, no client, no clock. The thread resource in, the document
out — subject as the title, one section per message in date order, the
plain-text body preferred (HTML converted by the Gmail client's own
extractor), attachment NAMES only, and a hard size cap.

Privacy: the document's display name is the subject, never a participant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from src.core.constants import GMAIL_FORMAT_FULL, RAG_MAIL_DOCUMENT_EXTENSION
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient

_DOCUMENT_NAME_MAX = 200


@dataclass(frozen=True, slots=True)
class RenderedThread:
    """A thread as the document the space will index.

    Attributes:
        markdown: The document body.
        subject: The thread's subject (first message carrying one), or its id.
        last_message_at: Newest message stamp — the change-detection key.
        message_count: Messages rendered.
        truncated: Whether the size cap cut the body.
    """

    markdown: str
    subject: str
    last_message_at: datetime | None
    message_count: int
    truncated: bool


def _message_at(message: dict[str, Any]) -> datetime | None:
    raw = message.get("internalDate")
    if not raw:
        return None
    try:
        return datetime.fromtimestamp(int(raw) / 1000, tz=UTC)
    except TypeError, ValueError, OverflowError:
        return None


def _attachment_names(message: dict[str, Any]) -> list[str]:
    """Attachment file names only — the content never enters a document."""
    payload = message.get("payload") or {}
    # The client's own MIME walk; the mail source has no second parser.
    parts = GoogleGmailClient._extract_attachment_info(payload)
    return [str(part["filename"]) for part in parts if part.get("filename")]


def _labels_of(thread: dict[str, Any]) -> set[str]:
    labels: set[str] = set()
    for message in thread.get("messages") or []:
        labels.update(str(label) for label in message.get("labelIds") or [])
    return labels


def thread_carries(thread: dict[str, Any], label_id: str) -> bool:
    """Whether any message of the thread carries the label (Gmail labels are per message)."""
    return label_id in _labels_of(thread)


def _thread_subject(messages: list[dict[str, Any]], thread: dict[str, Any]) -> str:
    """The first subject the thread carries, or its id — never a participant."""
    for message in messages:
        subject = str(message.get("subject") or "").strip()
        if subject:
            return subject
    return str(thread.get("id") or "")


def _render_message(message: dict[str, Any]) -> list[str]:
    """One message as its section: header line, recipients, body, attachment names."""
    at = _message_at(message)
    stamp = at.isoformat(timespec="minutes") if at is not None else ""
    lines = [f"## {stamp} {message.get('from') or ''}".strip()]
    for label, field in (("To", "to"), ("Cc", "cc")):
        if message.get(field):
            lines.append(f"{label}: {message[field]}")
    lines.append("")
    body = str(message.get("body") or message.get("snippet") or "").strip()
    if body:
        lines.extend([body, ""])
    names = _attachment_names(message)
    if names:
        lines.extend(["Attachments: " + ", ".join(names), ""])
    return lines


def _newest(messages: list[dict[str, Any]]) -> datetime | None:
    """The newest message stamp — the change-detection key."""
    stamps = [at for at in (_message_at(message) for message in messages) if at is not None]
    return max(stamps) if stamps else None


def render_thread(thread: dict[str, Any], *, max_chars: int) -> RenderedThread:
    """Render a Gmail thread as Markdown: subject, then one section per message.

    Messages are ordered by their internal date; the plain-text body is
    preferred and HTML is converted by the client's own extractor; attachments
    contribute their names only. The header labels are RFC names, not
    interface strings — the document is corpus, read by the retriever.

    Args:
        thread: The ``users.threads.get`` resource (``format=full``).
        max_chars: Hard size cap of the body; a cut ends with an ellipsis.

    Returns:
        The rendered document and its change-detection stamp.
    """
    messages = sorted(
        thread.get("messages") or [],
        key=lambda message: int(message.get("internalDate") or 0),
    )
    for message in messages:
        GoogleGmailClient._normalize_message_fields(message, GMAIL_FORMAT_FULL)
    lines: list[str] = [f"# {_thread_subject(messages, thread)}", ""]
    for message in messages:
        lines.extend(_render_message(message))
    body_text = "\n".join(lines).rstrip() + "\n"
    truncated = len(body_text) > max_chars
    if truncated:
        body_text = body_text[:max_chars].rstrip() + "\n…\n"
    return RenderedThread(
        body_text, _thread_subject(messages, thread), _newest(messages), len(messages), truncated
    )


#: A subject is written by a third party: control characters and path
#: separators never reach a stored display name (the file on disk is a UUID,
#: but the name travels into headers, archives and the interface).
_UNSAFE_NAME_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f/\\]+")


def document_name(rendered: RenderedThread, thread_id: str) -> str:
    """The display name: the subject (never a participant), or the thread id.

    Args:
        rendered: The rendered thread.
        thread_id: Fallback identity when the thread carries no subject.

    Returns:
        A bounded, control-character-free ``.md`` name.
    """
    base = _UNSAFE_NAME_CHARS.sub(" ", rendered.subject or "").strip() or thread_id
    return f"{base[:_DOCUMENT_NAME_MAX]}{RAG_MAIL_DOCUMENT_EXTENSION}"
